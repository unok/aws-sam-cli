"""SyncFlow Factory for creating SyncFlows based on resource types"""
import logging
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, cast

from samcli.lib.providers.provider import Stack, get_resource_by_id, ResourceIdentifier
from samcli.lib.sync.flows.auto_dependency_layer_sync_flow import AutoDependencyLayerParentSyncFlow
from samcli.lib.sync.flows.layer_sync_flow import LayerSyncFlow
from samcli.lib.utils.packagetype import ZIP, IMAGE
from samcli.lib.utils.resource_type_based_factory import ResourceTypeBasedFactory

from samcli.lib.sync.sync_flow import SyncFlow
from samcli.lib.sync.flows.function_sync_flow import FunctionSyncFlow
from samcli.lib.sync.flows.zip_function_sync_flow import ZipFunctionSyncFlow
from samcli.lib.sync.flows.image_function_sync_flow import ImageFunctionSyncFlow
from samcli.lib.sync.flows.rest_api_sync_flow import RestApiSyncFlow
from samcli.lib.sync.flows.http_api_sync_flow import HttpApiSyncFlow
from samcli.lib.sync.flows.stepfunctions_sync_flow import StepFunctionsSyncFlow
from samcli.lib.utils.boto_utils import get_boto_resource_provider_with_config
from samcli.lib.utils.cloudformation import get_physical_id_mapping
from samcli.lib.utils.resources import (
    AWS_SERVERLESS_FUNCTION,
    AWS_LAMBDA_FUNCTION,
    AWS_SERVERLESS_LAYERVERSION,
    AWS_LAMBDA_LAYERVERSION,
    AWS_SERVERLESS_API,
    AWS_APIGATEWAY_RESTAPI,
    AWS_SERVERLESS_HTTPAPI,
    AWS_APIGATEWAY_V2_API,
    AWS_SERVERLESS_STATEMACHINE,
    AWS_STEPFUNCTIONS_STATEMACHINE,
)

if TYPE_CHECKING:  # pragma: no cover
    from samcli.commands.deploy.deploy_context import DeployContext
    from samcli.commands.build.build_context import BuildContext

LOG = logging.getLogger(__name__)


class SyncFlowFactory(ResourceTypeBasedFactory[SyncFlow]):  # pylint: disable=E1136
    """Factory class for SyncFlow
    Creates appropriate SyncFlow types based on stack resource types
    """

    _deploy_context: "DeployContext"
    _build_context: "BuildContext"
    _physical_id_mapping: Dict[str, str]
    _auto_dependency_layer: bool

    def __init__(
        self,
        build_context: "BuildContext",
        deploy_context: "DeployContext",
        stacks: List[Stack],
        auto_dependency_layer: bool,
    ) -> None:
        """
        Parameters
        ----------
        build_context : BuildContext
            BuildContext to be passed into each individual SyncFlow
        deploy_context : DeployContext
            DeployContext to be passed into each individual SyncFlow
        stacks : List[Stack]
            List of stacks containing a root stack and optional nested ones
        """
        super().__init__(stacks)
        self._deploy_context = deploy_context
        self._build_context = build_context
        self._auto_dependency_layer = auto_dependency_layer
        self._physical_id_mapping = dict()

    def load_physical_id_mapping(self) -> None:
        """Load physical IDs of the stack resources from remote"""
        LOG.debug("Loading physical ID mapping")
        self._physical_id_mapping = get_physical_id_mapping(
            get_boto_resource_provider_with_config(
                region_name=self._deploy_context.region if self._deploy_context.region else None
            ),
            self._deploy_context.stack_name,
        )

    def _create_lambda_flow(
        self, resource_identifier: ResourceIdentifier, resource: Dict[str, Any]
    ) -> Optional[FunctionSyncFlow]:
        package_type = resource.get("Properties", dict()).get("PackageType", ZIP)
        if package_type == ZIP:
            if self._auto_dependency_layer:
                return AutoDependencyLayerParentSyncFlow(
                    str(resource_identifier),
                    self._build_context,
                    self._deploy_context,
                    self._physical_id_mapping,
                    self._stacks,
                )

            return ZipFunctionSyncFlow(
                str(resource_identifier),
                self._build_context,
                self._deploy_context,
                self._physical_id_mapping,
                self._stacks,
            )
        if package_type == IMAGE:
            return ImageFunctionSyncFlow(
                str(resource_identifier),
                self._build_context,
                self._deploy_context,
                self._physical_id_mapping,
                self._stacks,
            )
        return None

    def _create_layer_flow(self, resource_identifier: ResourceIdentifier, resource: Dict[str, Any]) -> SyncFlow:
        return LayerSyncFlow(
            str(resource_identifier),
            self._build_context,
            self._deploy_context,
            self._physical_id_mapping,
            self._stacks,
        )

    def _create_rest_api_flow(self, resource_identifier: ResourceIdentifier, resource: Dict[str, Any]) -> SyncFlow:
        return RestApiSyncFlow(
            str(resource_identifier),
            self._build_context,
            self._deploy_context,
            self._physical_id_mapping,
            self._stacks,
        )

    def _create_api_flow(self, resource_identifier: ResourceIdentifier, resource: Dict[str, Any]) -> SyncFlow:
        return HttpApiSyncFlow(
            str(resource_identifier),
            self._build_context,
            self._deploy_context,
            self._physical_id_mapping,
            self._stacks,
        )

    def _create_stepfunctions_flow(
        self, resource_identifier: ResourceIdentifier, resource: Dict[str, Any]
    ) -> Optional[SyncFlow]:
        definition_substitutions = resource.get("Properties", dict()).get("DefinitionSubstitutions", None)
        if definition_substitutions:
            LOG.warning(
                "DefinitionSubstitutions property is specified in resource %s. Skipping this resource. "
                "Code sync for StepFunctions does not go through CFN, please run sam sync --infra to update.",
                resource_identifier,
            )
            return None
        return StepFunctionsSyncFlow(
            str(resource_identifier),
            self._build_context,
            self._deploy_context,
            self._physical_id_mapping,
            self._stacks,
        )

    GeneratorFunction = Callable[["SyncFlowFactory", ResourceIdentifier, Dict[str, Any]], Optional[SyncFlow]]
    GENERATOR_MAPPING: Dict[str, GeneratorFunction] = {
        AWS_LAMBDA_FUNCTION: _create_lambda_flow,
        AWS_SERVERLESS_FUNCTION: _create_lambda_flow,
        AWS_SERVERLESS_LAYERVERSION: _create_layer_flow,
        AWS_LAMBDA_LAYERVERSION: _create_layer_flow,
        AWS_SERVERLESS_API: _create_rest_api_flow,
        AWS_APIGATEWAY_RESTAPI: _create_rest_api_flow,
        AWS_SERVERLESS_HTTPAPI: _create_api_flow,
        AWS_APIGATEWAY_V2_API: _create_api_flow,
        AWS_SERVERLESS_STATEMACHINE: _create_stepfunctions_flow,
        AWS_STEPFUNCTIONS_STATEMACHINE: _create_stepfunctions_flow,
    }

    # SyncFlow mapping between resource type and creation function
    # Ignoring no-self-use as PyLint has a bug with Generic Abstract Classes
    def _get_generator_mapping(self) -> Dict[str, GeneratorFunction]:  # pylint: disable=no-self-use
        return SyncFlowFactory.GENERATOR_MAPPING

    def create_sync_flow(self, resource_identifier: ResourceIdentifier) -> Optional[SyncFlow]:
        resource = get_resource_by_id(self._stacks, resource_identifier)
        generator = self._get_generator_function(resource_identifier)
        if not generator or not resource:
            return None
        return cast(SyncFlowFactory.GeneratorFunction, generator)(self, resource_identifier, resource)
