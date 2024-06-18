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
import rasterio
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
    parameter_help_link = 'user_manual_qax_ggoutlier.html#input-parameters'

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

        self.points_total: int | None = None
        self.points_outside_spec: int | None = None
        self.points_outside_spec_percentage: float | None = None

        self.spatial_outputs_export = False
        self.spatial_outputs_export_location = None
        self.spatial_outputs_qajson = True

        self.max_geojson_points = 2000
        self.max_geojson_points_exceeded = False

        self.geojson_point_features: list[geojson.Feature] = []
        self.extents_geojson = geojson.MultiPolygon()

        self.messages: list[str] = []
        self.passed = False

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
        args += ['-standard', self.standard]
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

    def _get_ggoutlier_log(self) -> Path | None:
        path = self.temp_base_dir / 'GGOutlier_log.txt'
        if not path.exists():
            return None
        # Return the first file found, GGOutlier only generates one shp file
        # per input
        return path

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
                    self.messages.append(
                        "Note: number of outliers identified exceeds that which can be "
                        "displayed within QAX. Please view shp file included in the "
                        "detailed spatial outputs for all outlier locations."
                    )
                    LOG.debug("Exceeded geojson point count")
                    break

                # Move to the next feature
                feature = layer.GetNextFeature()

        # Cleanup
        datasource = None

    def __process_ggoutlier_log_line(self, log_line: str) -> None:
        """ Extracts information from a log line if relevant
        """
        if ":Points checked:" in log_line:
            # process line formatted like
            #     INFO:root:Points checked: 28,613,210
            s = log_line.split(":Points checked:",1)[1].strip()
            s = s.replace(',','')
            self.points_total = int(s)
        elif ":Points outside specification:" in log_line:
            # process line formatted like
            #     INFO:root:Points outside specification: 1,250
            s = log_line.split(":Points outside specification:",1)[1].strip()
            s = s.replace(',','')
            self.points_outside_spec = int(s)
        elif ":Percentage outside specification:" in log_line:
            # process line formatted like
            #     INFO:root:Percentage outside specification: 0.0043686
            s = log_line.split(":Percentage outside specification:",1)[1].strip()
            s = s.replace(',','')
            self.points_outside_spec_percentage = float(s)

    def _process_ggoutlier_log(self, log_file: Path) -> None:
        """ Reads summary information from GGOutlier log file to be included
        in QAX details. This information is also used to determine if check
        passed or failed.
        """
        LOG.debug(f"Processing GGOutlier log: {str(log_file)}")

        with open(log_file) as fp:
            for line in fp:
                try:
                    self.__process_ggoutlier_log_line(line)
                except Exception as ex:
                    raise RuntimeError(f"Error parsing log line: {line}") from ex

    def _extract_extents(self) -> geojson.MultiPolygon:
        """ Generates geojson extents from input grid file
        """
        extents: geojson.MultiPolygon | None = None
        with rasterio.open(str(self.grid_file)) as src_grid:
            bounds = src_grid.bounds

            # need to transform into wsg84 for geojson
            ogr_srs = osr.SpatialReference()
            ogr_srs.ImportFromWkt(src_grid.crs.to_wkt())
            ogr_srs_out = osr.SpatialReference()
            ogr_srs_out.ImportFromEPSG(4326)
            transform = osr.CoordinateTransformation(ogr_srs, ogr_srs_out)

            transformed_bounds = transform.TransformBounds(
                bounds.left,
                bounds.bottom,
                bounds.right,
                bounds.top,
                2
            )
            minx, miny, maxx, maxy = transformed_bounds

            extents = geojson.MultiPolygon([[[
                (miny, minx),
                (miny, maxx),
                (maxy, maxx),
                (maxy, minx),
            ]]])
        return extents

    def run(self) -> None:
        """
        Runs GGOutlier over all the input grid files that have been provided
        """
        LOG.info(f"Grid file: {self.grid_file}")
        LOG.info(f"Standard: {self.standard}")
        LOG.info(f"Near: {self.near}")
        LOG.info(f"Verbose: {self.verbose}")

        LOG.info(f"Output folder: {self.outdir}")

        self.extents_geojson = self._extract_extents()

        # import contextlib
        # with contextlib.nullcontext(tempfile.mkdtemp()) as tmpdir:
        # Note: TemporaryDirectory is automatically deleted, use the above to debug
        # as tempfile.mkdtemp isn't automatically deleted
        with tempfile.TemporaryDirectory(suffix=".ggoutlier-check") as tmpdir:
            self.temp_base_dir = Path(tmpdir)
            cmd_args = self.__get_ggoutlier_cmd_args()
            LOG.debug(f"GGOutlier args: {' '.join(cmd_args)}")

            # GGOutlier uses the root logger to generate a log file
            # The report GGOutlier generates reads this log file and extracts
            # file paths from it. It assumes it's the root logger that has
            # generated the log file.
            # This means we have to temporarily switch out the root logger
            # and switch back (see finally block below) once GGOutlier is complete
            old_root_logger = logging.root
            logging.root = logging.Logger("root", level=logging.INFO)

            try:
                # run GGOutlier
                ggoutlier.main(cmd_args)
            except Exception as ex:
                raise ex
            finally:
                logging.root = old_root_logger

            # we use the points in the shp generated by GGOutlier to populated the geojson
            # data that gets included in the checks QAJSON
            shp_file = self._get_ggoutlier_shp()
            if not shp_file:
                self.messages.append("Unable to find GGOutlier generated shp file, results cannot be extracted")
                LOG.info("Unable to find GGOutlier generated shp file, results cannot be extracted")
            else:
                self._process_ggoutlier_shp(shp_file)

            # we extract some metrics from what GGOutlier includes in its log
            log_file = self._get_ggoutlier_log()
            if not log_file:
                self.messages.append("Unable to find GGOutlier generated log file, results cannot be extracted")
                LOG.info("Unable to find GGOutlier generated log file, results cannot be extracted")
            else:
                self.passed = False
                self._process_ggoutlier_log(log_file)

            if self.spatial_outputs_export:
                # if we don't move the temp data it will be automatically cleaned up
                self._move_tmp_dir()

        # In future a threshold may be more appropriate, this will fail the check even
        # if only one outlier is found
        if self.points_outside_spec > 0:
            self.passed = False
        else:
            self.passed = True
