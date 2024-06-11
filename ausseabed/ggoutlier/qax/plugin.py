from datetime import datetime
from ggoutlier import cloud2tif
import logging
import traceback
from typing import Callable, Any
from pathlib import Path

from hyo2.qax.lib.plugin import QaxCheckToolPlugin, QaxCheckReference, \
    QaxFileType
from ausseabed.qajson.model import QajsonRoot, QajsonDataLevel, QajsonCheck, \
    QajsonFile, QajsonInputs, QajsonExecution, QajsonOutputs

from ausseabed.ggoutlier.ggoutlier_check import GgoutlierCheck

LOG = logging.getLogger(__name__)


class GgoutlierQaxPlugin(QaxCheckToolPlugin):

    # supported file types
    file_types = [
        QaxFileType(
            name="GeoTIFF",
            extension="tif",
            group="Survey DTMs",
            icon="tif.png"
        ),
    ]

    def __init__(self):
        super(GgoutlierQaxPlugin, self).__init__()
        # name of the check tool
        self.name = 'GGOutlier Checks'
        self._check_references = self._build_check_references()

    def _build_check_references(self) -> list[QaxCheckReference]:
        data_level = "survey_products"
        check_refs = []

        cr = QaxCheckReference(
            id=GgoutlierCheck.id,
            name=GgoutlierCheck.name,
            data_level=data_level,
            description=None,
            supported_file_types=GgoutlierQaxPlugin.file_types,
            default_input_params=GgoutlierCheck.input_params,
            version=GgoutlierCheck.version,
        )
        check_refs.append(cr)
        return check_refs

    def checks(self) -> list[QaxCheckReference]:
        return self._check_references

    def _get_param_value(self, param_name: str, check: QajsonCheck) -> Any:
        ''' Gets a parameter value from the QajsonCheck based on the parameter
        name. Will return None if the parameter is not found.
        '''
        param = next(
            (
                p
                for p in check.inputs.params
                if p.name == param_name
            ),
            None
        )
        if param is None:
            return None
        else:
            return param.value


    def _run_ggoutlier_check(self, check: QajsonCheck):
        # get the parameter values the check needs to run
        input_standard = self._get_param_value(
            'Standard',
            check
        )
        input_near = int(self._get_param_value(
            'Near',
            check
        ))
        input_verbose = bool(self._get_param_value(
            'Verbose',
            check
        ))

        # get the input files the check needs to run. In this case we get
        # the first grid file that contains a depth band
        grid_file = None
        for f in check.inputs.files:
            if f.file_type == 'Survey DTMs':
                qajson_input_file = Path(f.path)
                # ggoutlier include some util classes we can use to get details
                # from the raster file
                band_names = cloud2tif.getbandnames(f.path)
                band_names = list(map(lambda x: x.lower(), band_names))

                # if there's a single band tif, and it has depth in the filename
                # then use it
                if 'depth' in qajson_input_file.name.lower() and len(band_names) == 1:
                    grid_file = qajson_input_file
                    break

                # if it's a single or multiband tif, and depth is one of the band
                # names included in the tifs metadata, then use it
                if 'depth' in band_names:
                    grid_file = qajson_input_file
                    break

        output_details = QajsonOutputs()
        check.outputs = output_details

        start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")
        execution_details = QajsonExecution(
            start=start_time,
            end=None,
            status='running',
            error=None
        )
        check.outputs.execution = execution_details

        if grid_file is None:
            msg = "Missing input depth data"
            LOG.info(msg)
            execution_details.status = "aborted"
            execution_details.error = msg

        if execution_details.status == "aborted":
            msg = "Aborting GGOutlier Check"
            LOG.info(msg)
            return

        if self.spatial_outputs_export:
            outdir = Path(self.spatial_outputs_export_location)
        else:
            outdir = None

        ggo_check = GgoutlierCheck(
            grid_file=grid_file,
            standard=input_standard,
            near=input_near,
            verbose=input_verbose,
            outdir=outdir
        )
        ggo_check.spatial_outputs_export = self.spatial_outputs_qajson
        ggo_check.spatial_outputs_export_location = self.spatial_outputs_export_location
        ggo_check.spatial_outputs_qajson = self.spatial_outputs_qajson

        try:
            # now run the check
            ggo_check.run()

            execution_details.status = 'completed'
        except Exception as ex:
            execution_details.status = 'failed'
            execution_details.error = traceback.format_exc()
        finally:
            execution_details.end = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")

        if execution_details.status == 'failed':
            # no need to populate results as there are none
            return

        # now add the result data to the qajson output details so that it's
        # captured and presented to the user
        if ggo_check.passed:
            output_details.check_state = 'pass'
        else:
            output_details.check_state = 'fail'

        # pass_percentage = (density_check.total_nodes - density_check.failed_nodes) / density_check.total_nodes

        messages: list[str] = []
        messages.append("check message")

        output_details.messages = messages

        # use the data dict to stash some misc information generated by the check
        data = {}

        # if self.spatial_outputs_qajson:
        #     # the qax viewer isn't designed to be an all bells viewing solution
        #     # nor replace tools like QGIS, TuiView ...
        #     # the vector geoms need to be simplified, and all geoms transformed
        #     # to epsg:4326
        #     # other plugins use a buffer of 5 pixel widths and then simplify

        #     with rasterio.open(grid_file) as ds:
        #         # bounds derived from input raster
        #         gdf_box = geopandas.GeoDataFrame(
        #             {"geometry": [geometry.box(*ds.bounds)]},
        #             crs=ds.crs,
        #         ).to_crs(epsg=4326)

        #         # buffering; assuming square-ish pixels ...
        #         distance = 5*ds.res[0]  # used for buffering and simplifying
        #         buffered = density_check.gdf.buffer(distance)

        #         # false means use the "Douglas-Peucker algorithm"
        #         simplified_geom = buffered.simplify(
        #             distance, preserve_topology=False
        #         )
        #         warped_geom = simplified_geom.to_crs(epsg=4326)

        #         # qax map viewer requires MultiPolygon geoms
        #         mp_box_geoms = geometry.MultiPolygon(gdf_box.geometry.values)
        #         mp_pix_geoms = geometry.MultiPolygon(
        #             warped_geom.geometry.values,
        #         )

        #         data['map'] = geometry.mapping(mp_box_geoms)
        #         data['extents'] = geometry.mapping(mp_pix_geoms)

        output_details.data = data

    def run(
        self,
        qajson: QajsonRoot,
        progress_callback: Callable = None,
        qajson_update_callback: Callable = None,
        is_stopped: Callable = None
    ) -> None:
        ''' Run all checks implemented by this plugin
        '''
        # get all survey product checks, the check references we create in
        # _build_check_references all specify "survey_products" so we'll only
        # find the input details for this plugin here
        sp_qajson_checks = qajson.qa.survey_products.checks

        for qajson_check in sp_qajson_checks:
            if is_stopped is not None and is_stopped():
                # stop looping through checks if the user has stopped them
                break
            # loop through all the checks, this will include checks implemented in
            # other plugins (we need to skip these)
            if qajson_check.info.id == GgoutlierCheck.id:
                # then run the ggoutlier check
                self._run_ggoutlier_check(qajson_check)
            # other checks would be added here

        if qajson_update_callback is not None:
            qajson_update_callback()
