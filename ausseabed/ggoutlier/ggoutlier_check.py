"""
GGOutlier check
- passes a simple set of inputs to the main function of ggoutlier
- runs ggoutlier
- extracts QAX summary information from GGOutlier output files
- moves outputs to QAX 'detailed spatial outputs' folder
"""

import geojson.geometry
from osgeo import ogr, osr
from pathlib import Path
from typing import Optional
import distutils
import geojson
import ggoutlier
import glob
import json
import logging
import os
import shutil
import tempfile

from ausseabed.qajson.model import QajsonParam, QajsonOutputs, QajsonExecution


LOG = logging.getLogger(__name__)


class GgoutlierCheck:
    # details used by the QAX plugin
    id = "ec2d2ebc-480e-44d8-a5c5-c9dec4f8428a"
    name = "GGOutlier Check"
    version = "1"
    input_params = [
        QajsonParam(
            "Standard",
            "order1a",
            [
                "order2", "order1b", "order1a", "specialorder", "exclusiveorder", "hipp1", "hipp2", "hippassage"
            ]
        ),
        QajsonParam("Near", 5),
        QajsonParam("Verbose", False),
    ]

    def __init__(
        self,
        grid_file: Path,
        standard: str,
        near: bool,
        verbose: bool,
        outdir: Optional[Path] = None
    ) -> None:
        self.grid_file = grid_file
        self.outdir = outdir
        self.standard = standard
        self.near = near
        self.verbose = verbose

        self.spatial_outputs_export = False
        self.spatial_outputs_export_location = None
        self.spatial_outputs_qajson = True

        self.max_geojson_points = 2000
        self.max_geojson_points_exceeded = False

        self.geojson_point_features: list[geojson.Feature] = []
        self.extents_geojson = geojson.MultiPolygon()

        self.messages: list[str] = []

    def _get_output_file_location(
            self
        ) -> str:
        if self.spatial_outputs_export_location is None:
            return None
        check_path = os.path.join(self.grid_file.stem, self.name)
        return os.path.join(self.spatial_outputs_export_location, check_path)

    def __get_ggoutlier_cmd_args(self) -> list[str]:
        """ Build a list of strings that mimic what a user would provide to ggoutlier
        as command line args.
        """
        args: list[str] = []
        args += ['-i', str(self.grid_file.absolute())]
        args += ['-near', str(self.near)]
        # args += ['-standard', self.standard]
        args += ['-standard', 'order1b']
        if self.verbose:
            args += ['-verbose']
        args += ['-odir', str(self.temp_base_dir.absolute())]

        return args

    def _move_tmp_dir(self):
        ol = self._get_output_file_location()
        LOG.debug(f"Moving GGOutlier output: {str(self.temp_base_dir)} to {ol}")
        distutils.dir_util.copy_tree(
            str(self.temp_base_dir.absolute()),
            ol)

    def _get_ggoutlier_shp(self) -> Path | None:
        pattern = os.path.join(str(self.temp_base_dir.absolute()), '*.shp')
        files = glob.glob(pattern)
        if not files:
            return None
        # Return the first file found, GGOutlier only generates one shp file
        # per input
        return Path(files[0])

    def _process_ggoutlier_shp(self, shp_file: Path) -> None:
        LOG.debug(f"Processing GGOutlier shp: {str(shp_file)}")
        fn = str(shp_file.absolute())
        datasource = ogr.Open(fn)
        if not datasource:
            raise Exception(f"Could not open file: {fn}")

        # we're
        layer_count = datasource.GetLayerCount()
        LOG.debug(f"Found {str(layer_count)} layers")

        feature_id = 0
        for layer_index in range(layer_count):
            layer = datasource.GetLayerByIndex(layer_index)
            # layer_name = layer.GetName()

            layer_spatial_ref = layer.GetSpatialRef().ExportToWkt()

            # setup a coordinate transform, we need points in WSG84 (4326)
            # for geojson
            src_proj = osr.SpatialReference()
            src_proj.ImportFromWkt(layer_spatial_ref)
            dst_proj = osr.SpatialReference()
            dst_proj.ImportFromEPSG(4326)
            dst_proj.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            coord_trans = osr.CoordinateTransformation(src_proj, dst_proj)

            feature = layer.GetNextFeature()
            while feature:
                # Extract feature attributes
                attributes = {}
                for i in range(feature.GetFieldCount()):
                    field_name = feature.GetFieldDefnRef(i).GetName()
                    field_value = feature.GetField(i)
                    attributes[field_name] = field_value

                # Extract feature geometry
                geometry = feature.GetGeometryRef()
                if geometry.GetGeometryName() == 'POINT':
                    # Extract the point coordinates in the shp file CRS
                    x = geometry.GetX()
                    y = geometry.GetY()
                    # convert to geojson CRS
                    x, y = coord_trans.TransformPoint(x, y, 0.0)[:2]
                    geom = geojson.geometry.Point([x, y])
                    feat = geojson.Feature(
                        id=feature_id,
                        geometry=geom,
                        properties=attributes
                    )
                    self.geojson_point_features.append(feat)

                feature_id += 1

                if feature_id > self.max_geojson_points:
                    # qajson gets large if too many points are included in the output.
                    # So limit the maximum anount of points. This doesnt effect the
                    # reported stats, only what is shown in the map widget.
                    self.max_geojson_points_exceeded = True
                    LOG.debug("Exceeded geojson point count")
                    break

                # Move to the next feature
                feature = layer.GetNextFeature()

        # Cleanup
        datasource = None

    def run(self) -> None:
        """
        Runs GGOutlier over all the input grid files that have been provided
        """
        LOG.info(f"Grid file: {self.grid_file}")
        LOG.info(f"Standard: {self.standard}")
        LOG.info(f"Near: {self.near}")
        LOG.info(f"Verbose: {self.verbose}")

        LOG.info(f"Output folder: {self.outdir}")

        self.passed = True

        with tempfile.TemporaryDirectory(suffix=".ggoutlier-check") as tmpdir:
            self.temp_base_dir = Path(tmpdir)
            cmd_args = self.__get_ggoutlier_cmd_args()
            LOG.debug(f"GGOutlier args: {' '.join(cmd_args)}")

            # run GGOutlier
            ggoutlier.main(cmd_args)

            shp_file = self._get_ggoutlier_shp()
            if not shp_file:
                self.messages.append("Unable to find GGOutlier generated shp file, results cannot be extracted")
            else:
                self._process_ggoutlier_shp(shp_file)

            LOG.info("self.spatial_outputs_export " + str(self.spatial_outputs_export))
            if self.spatial_outputs_export:
                self._move_tmp_dir()




        #     out_pathname = Path(tmpdir).joinpath("density.tif") 

        #     LOG.info("Calculating density")
        #     hist, bins, cell_count = pdal_pipeline.density(
        #         self.grid_file, self.point_cloud_file, out_pathname
        #     )  # noqa: E501

        #     LOG.info("Converting low density pixels to vector")
        #     gdf = utils.vectorise_low_density(out_pathname, self.minimum_count)

        #     if self.outdir is not None:
        #         outdir = self.outdir / self.point_cloud_file.stem / self.name
        #         outdir.mkdir(parents=True, exist_ok=True)

        #         _ = shutil.copy(out_pathname, outdir)

        #         gdf_pathname = outdir / "low-density-pixels.shp"
        #         gdf.to_file(gdf_pathname, driver="ESRI Shapefile")

        # failed_nodes = int(hist[0:self.minimum_count].sum())
        # percentage = float((failed_nodes / cell_count) * 100)
        # percentage_passed = 100 - percentage
        # passed = percentage_passed > self.minimum_count_percentage

        # # total number of non-nodata nodes in grid
        # self.total_nodes = cell_count

        # # total number of nodes that failed density check
        # self.failed_nodes = failed_nodes
        # self.percentage_failed = percentage
        # self.percentage_passed = percentage_passed

        # self.passed = passed

        # # (density, number of cells that have that density)
        # self.histogram = list(zip(bins.tolist(), hist.tolist()))

        # self.gdf = gdf

        # LOG.info(cell_count)
        # LOG.info(passed)
        # LOG.info(percentage_passed)
        # LOG.info(percentage)
        # LOG.info(failed_nodes)
