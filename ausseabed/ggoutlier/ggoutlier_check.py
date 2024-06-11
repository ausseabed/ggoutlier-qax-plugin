"""
Resolution independent density check
"""

from pathlib import Path
from typing import Optional
import distutils
import ggoutlier
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
