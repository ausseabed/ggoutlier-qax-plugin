"""
Resolution independent density check
"""

from pathlib import Path
from typing import Optional
import tempfile
import json
import shutil
import logging

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

    def run(self):
        """
        Runs GGOutlier over all the input grid files that have been provided
        """
        LOG.info(f"Grid file: {self.grid_file}")
        LOG.info(f"Standard: {self.standard}")
        LOG.info(f"Near: {self.near}")
        LOG.info(f"Verbose: {self.verbose}")

        LOG.info(f"Output folder: {self.outdir}")

        self.passed = True

        # with tempfile.TemporaryDirectory(suffix=".density-check") as tmpdir:
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
