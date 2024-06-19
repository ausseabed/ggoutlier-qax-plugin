from datetime import datetime
from ggoutlier import cloud2tif
import geojson
import logging
import os
import rasterio
import traceback
from typing import Callable, Any
from pathlib import Path

from hyo2.qax.lib.plugin import QaxCheckToolPlugin, QaxCheckReference, \
    QaxFileType
from ausseabed.qajson.model import QajsonRoot, QajsonDataLevel, QajsonCheck, \
    QajsonFile, QajsonInputs, QajsonExecution, QajsonOutputs

from ausseabed.ggoutlier.lib.ggoutlier_check import GgoutlierCheck

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
            parameter_help_link=GgoutlierCheck.parameter_help_link,
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
            state_msg = f"No outliers found, {ggo_check.points_total} were checked"
        else:
            output_details.check_state = 'fail'
            state_msg = (
                f"{ggo_check.points_outside_spec} outliers were found in a total "
                f"of {ggo_check.points_total} points. This represents a percentage of "
                f"{ggo_check.points_outside_spec_percentage:.3f}%"
            )

        messages: list[str] = []
        messages.append(state_msg)
        messages.extend(ggo_check.messages)

        output_details.messages = messages

        # use the data dict to stash some misc information generated by the check
        data = {}

        if self.spatial_outputs_qajson and execution_details.status == 'completed':
            # then we can include some geojson in the qajson output
            json_map_feature = geojson.FeatureCollection(ggo_check.geojson_point_features)
            json_map = geojson.mapping.to_mapping(json_map_feature)
            data['map'] = json_map
            data['extents'] = ggo_check.extents_geojson

        if execution_details.status == 'completed':
            data['points_outside_spec'] = ggo_check.points_outside_spec
            data['points_total'] = ggo_check.points_total
            data['points_outside_spec_percentage'] = ggo_check.points_outside_spec_percentage

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

    # This info is presented in the QAX UI details column
    def get_file_details(self, filename: str) -> str:
        """ Return some details about the raster file that's been provided. In this
        case a list of the bands, and the resolution of the dataset.
        """
        res: list[str] = []

        band_names: list[str] = cloud2tif.getbandnames(filename)
        for band_name in band_names:
            if band_name is None:
                if 'depth' in Path(filename).stem.lower():
                    res.append('depth')
                elif 'density' in Path(filename).stem.lower():
                    res.append('density')
                elif 'uncertainty' in Path(filename).stem.lower():
                    res.append('uncertainty')
                else:
                    res.append(f"Could not identify name in: {Path(filename).stem}")
            else:
                res.append(band_name)

        with rasterio.open(filename) as dataset:
            width = dataset.width
            height = dataset.height
            res.append(f"{width}{chr(0x00D7)}{height}")

        return "\n".join(res)
