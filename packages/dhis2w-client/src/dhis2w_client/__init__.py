"""Async DHIS2 API client with pluggable auth and pydantic models."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

# Lazy surface (PEP 562): importing `dhis2w_client` no longer eagerly pulls
# the full v42 tree (incl. the 17k-line generated OAS models). Each public
# symbol resolves to its module on first attribute access. The TYPE_CHECKING
# block gives type checkers + IDEs the real symbols; __getattr__ serves them
# at runtime. This keeps `from dhis2w_client import X` cheap on the CLI start
# path while preserving the published import surface.
if TYPE_CHECKING:
    from dhis2w_client.errors import (
        AuthenticationError as AuthenticationError,
    )
    from dhis2w_client.errors import (
        Dhis2ApiError as Dhis2ApiError,
    )
    from dhis2w_client.errors import (
        Dhis2ClientError as Dhis2ClientError,
    )
    from dhis2w_client.errors import (
        OAuth2FlowError as OAuth2FlowError,
    )
    from dhis2w_client.errors import (
        UnsupportedVersionError as UnsupportedVersionError,
    )
    from dhis2w_client.generated import Dhis2 as Dhis2
    from dhis2w_client.profile import (
        PROFILE_NAME_MAX_LEN as PROFILE_NAME_MAX_LEN,
    )
    from dhis2w_client.profile import (
        InvalidProfileNameError as InvalidProfileNameError,
    )
    from dhis2w_client.profile import (
        NoProfileError as NoProfileError,
    )
    from dhis2w_client.profile import (
        Profile as Profile,
    )
    from dhis2w_client.profile import (
        UnknownProfileError as UnknownProfileError,
    )
    from dhis2w_client.profile import (
        profile_from_env_raw as profile_from_env_raw,
    )
    from dhis2w_client.profile import (
        validate_profile_name as validate_profile_name,
    )
    from dhis2w_client.v42.aggregate import DataValue as DataValue
    from dhis2w_client.v42.aggregate import DataValueSet as DataValueSet
    from dhis2w_client.v42.analytics import (
        AnalyticsMetaData as AnalyticsMetaData,
    )
    from dhis2w_client.v42.analytics import (
        Grid as Grid,
    )
    from dhis2w_client.v42.analytics import (
        GridHeader as GridHeader,
    )
    from dhis2w_client.v42.analytics_stream import AnalyticsAccessor as AnalyticsAccessor
    from dhis2w_client.v42.apps import (
        App as App,
    )
    from dhis2w_client.v42.apps import (
        AppHubApp as AppHubApp,
    )
    from dhis2w_client.v42.apps import (
        AppHubVersion as AppHubVersion,
    )
    from dhis2w_client.v42.apps import (
        AppsAccessor as AppsAccessor,
    )
    from dhis2w_client.v42.apps import (
        AppSnapshotEntry as AppSnapshotEntry,
    )
    from dhis2w_client.v42.apps import (
        AppsSnapshot as AppsSnapshot,
    )
    from dhis2w_client.v42.apps import (
        AppStatus as AppStatus,
    )
    from dhis2w_client.v42.apps import (
        AppType as AppType,
    )
    from dhis2w_client.v42.apps import (
        RestoreOutcome as RestoreOutcome,
    )
    from dhis2w_client.v42.apps import (
        RestoreSummary as RestoreSummary,
    )
    from dhis2w_client.v42.attribute_values import AttributeValuesAccessor as AttributeValuesAccessor
    from dhis2w_client.v42.auth.base import AuthProvider as AuthProvider
    from dhis2w_client.v42.auth.basic import BasicAuth as BasicAuth
    from dhis2w_client.v42.auth.oauth2 import (
        OAuth2Auth as OAuth2Auth,
    )
    from dhis2w_client.v42.auth.oauth2 import (
        OAuth2Token as OAuth2Token,
    )
    from dhis2w_client.v42.auth.oauth2 import (
        TokenStore as TokenStore,
    )
    from dhis2w_client.v42.auth.pat import PatAuth as PatAuth
    from dhis2w_client.v42.auth_schemes import (
        ApiHeadersAuthScheme as ApiHeadersAuthScheme,
    )
    from dhis2w_client.v42.auth_schemes import (
        ApiQueryParamsAuthScheme as ApiQueryParamsAuthScheme,
    )
    from dhis2w_client.v42.auth_schemes import (
        ApiTokenAuthScheme as ApiTokenAuthScheme,
    )
    from dhis2w_client.v42.auth_schemes import (
        AuthScheme as AuthScheme,
    )
    from dhis2w_client.v42.auth_schemes import (
        AuthSchemeAdapter as AuthSchemeAdapter,
    )
    from dhis2w_client.v42.auth_schemes import (
        HttpBasicAuthScheme as HttpBasicAuthScheme,
    )
    from dhis2w_client.v42.auth_schemes import (
        OAuth2ClientCredentialsAuthScheme as OAuth2ClientCredentialsAuthScheme,
    )
    from dhis2w_client.v42.auth_schemes import (
        auth_scheme_from_route as auth_scheme_from_route,
    )
    from dhis2w_client.v42.categories import CategoriesAccessor as CategoriesAccessor
    from dhis2w_client.v42.categories import Category as Category
    from dhis2w_client.v42.category_combo_builder import (
        CategoryBuildEntry as CategoryBuildEntry,
    )
    from dhis2w_client.v42.category_combo_builder import (
        CategoryComboBuildResult as CategoryComboBuildResult,
    )
    from dhis2w_client.v42.category_combo_builder import (
        CategoryComboBuildSpec as CategoryComboBuildSpec,
    )
    from dhis2w_client.v42.category_combo_builder import (
        CategoryOptionSpec as CategoryOptionSpec,
    )
    from dhis2w_client.v42.category_combo_builder import (
        CategorySpec as CategorySpec,
    )
    from dhis2w_client.v42.category_combo_builder import (
        build_category_combo as build_category_combo,
    )
    from dhis2w_client.v42.category_combos import (
        CategoryCombo as CategoryCombo,
    )
    from dhis2w_client.v42.category_combos import (
        CategoryCombosAccessor as CategoryCombosAccessor,
    )
    from dhis2w_client.v42.category_option_combos import (
        CategoryOptionCombo as CategoryOptionCombo,
    )
    from dhis2w_client.v42.category_option_combos import (
        CategoryOptionCombosAccessor as CategoryOptionCombosAccessor,
    )
    from dhis2w_client.v42.category_option_group_sets import (
        CategoryOptionGroupSet as CategoryOptionGroupSet,
    )
    from dhis2w_client.v42.category_option_group_sets import (
        CategoryOptionGroupSetsAccessor as CategoryOptionGroupSetsAccessor,
    )
    from dhis2w_client.v42.category_option_groups import (
        CategoryOptionGroup as CategoryOptionGroup,
    )
    from dhis2w_client.v42.category_option_groups import (
        CategoryOptionGroupsAccessor as CategoryOptionGroupsAccessor,
    )
    from dhis2w_client.v42.category_options import (
        CategoryOption as CategoryOption,
    )
    from dhis2w_client.v42.category_options import (
        CategoryOptionsAccessor as CategoryOptionsAccessor,
    )
    from dhis2w_client.v42.client import Dhis2Client as Dhis2Client
    from dhis2w_client.v42.client_context import (
        build_auth_for_basic as build_auth_for_basic,
    )
    from dhis2w_client.v42.client_context import (
        open_client as open_client,
    )
    from dhis2w_client.v42.customize import (
        CustomizationResult as CustomizationResult,
    )
    from dhis2w_client.v42.customize import (
        CustomizeAccessor as CustomizeAccessor,
    )
    from dhis2w_client.v42.customize import (
        LoginCustomization as LoginCustomization,
    )
    from dhis2w_client.v42.dashboards import DashboardsAccessor as DashboardsAccessor
    from dhis2w_client.v42.dashboards import DashboardSlot as DashboardSlot
    from dhis2w_client.v42.data_element_group_sets import (
        DataElementGroupSet as DataElementGroupSet,
    )
    from dhis2w_client.v42.data_element_group_sets import (
        DataElementGroupSetsAccessor as DataElementGroupSetsAccessor,
    )
    from dhis2w_client.v42.data_element_groups import (
        DataElementGroup as DataElementGroup,
    )
    from dhis2w_client.v42.data_element_groups import (
        DataElementGroupsAccessor as DataElementGroupsAccessor,
    )
    from dhis2w_client.v42.data_elements import DataElement as DataElement
    from dhis2w_client.v42.data_elements import DataElementsAccessor as DataElementsAccessor
    from dhis2w_client.v42.data_sets import DataSet as DataSet
    from dhis2w_client.v42.data_sets import DataSetsAccessor as DataSetsAccessor
    from dhis2w_client.v42.data_values import DataValuesAccessor as DataValuesAccessor
    from dhis2w_client.v42.datastore import DatastoreAccessor as DatastoreAccessor
    from dhis2w_client.v42.envelopes import (
        Conflict as Conflict,
    )
    from dhis2w_client.v42.envelopes import (
        ConflictRow as ConflictRow,
    )
    from dhis2w_client.v42.envelopes import (
        ErrorReport as ErrorReport,
    )
    from dhis2w_client.v42.envelopes import (
        ImportCount as ImportCount,
    )
    from dhis2w_client.v42.envelopes import (
        ImportReport as ImportReport,
    )
    from dhis2w_client.v42.envelopes import (
        ObjectReport as ObjectReport,
    )
    from dhis2w_client.v42.envelopes import (
        Stats as Stats,
    )
    from dhis2w_client.v42.envelopes import (
        TypeReport as TypeReport,
    )
    from dhis2w_client.v42.envelopes import (
        WebMessageResponse as WebMessageResponse,
    )
    from dhis2w_client.v42.files import (
        Document as Document,
    )
    from dhis2w_client.v42.files import (
        FileResource as FileResource,
    )
    from dhis2w_client.v42.files import (
        FileResourceDomain as FileResourceDomain,
    )
    from dhis2w_client.v42.files import (
        FilesAccessor as FilesAccessor,
    )
    from dhis2w_client.v42.indicator_group_sets import (
        IndicatorGroupSet as IndicatorGroupSet,
    )
    from dhis2w_client.v42.indicator_group_sets import (
        IndicatorGroupSetsAccessor as IndicatorGroupSetsAccessor,
    )
    from dhis2w_client.v42.indicator_groups import (
        IndicatorGroup as IndicatorGroup,
    )
    from dhis2w_client.v42.indicator_groups import (
        IndicatorGroupsAccessor as IndicatorGroupsAccessor,
    )
    from dhis2w_client.v42.indicators import Indicator as Indicator
    from dhis2w_client.v42.indicators import IndicatorsAccessor as IndicatorsAccessor
    from dhis2w_client.v42.json_patch import (
        AddOp as AddOp,
    )
    from dhis2w_client.v42.json_patch import (
        CopyOp as CopyOp,
    )
    from dhis2w_client.v42.json_patch import (
        JsonPatchOp as JsonPatchOp,
    )
    from dhis2w_client.v42.json_patch import (
        JsonPatchOpAdapter as JsonPatchOpAdapter,
    )
    from dhis2w_client.v42.json_patch import (
        MoveOp as MoveOp,
    )
    from dhis2w_client.v42.json_patch import (
        RemoveOp as RemoveOp,
    )
    from dhis2w_client.v42.json_patch import (
        ReplaceOp as ReplaceOp,
    )
    from dhis2w_client.v42.json_patch import (
        TestOp as TestOp,
    )
    from dhis2w_client.v42.legend_sets import (
        Legend as Legend,
    )
    from dhis2w_client.v42.legend_sets import (
        LegendSet as LegendSet,
    )
    from dhis2w_client.v42.legend_sets import (
        LegendSetsAccessor as LegendSetsAccessor,
    )
    from dhis2w_client.v42.legend_sets import (
        LegendSetSpec as LegendSetSpec,
    )
    from dhis2w_client.v42.legend_sets import (
        LegendSpec as LegendSpec,
    )
    from dhis2w_client.v42.maintenance import (
        DataIntegrityCheck as DataIntegrityCheck,
    )
    from dhis2w_client.v42.maintenance import (
        DataIntegrityIssue as DataIntegrityIssue,
    )
    from dhis2w_client.v42.maintenance import (
        DataIntegrityReport as DataIntegrityReport,
    )
    from dhis2w_client.v42.maintenance import (
        DataIntegrityResult as DataIntegrityResult,
    )
    from dhis2w_client.v42.maintenance import (
        IntegrityIssueRow as IntegrityIssueRow,
    )
    from dhis2w_client.v42.maintenance import (
        JobType as JobType,
    )
    from dhis2w_client.v42.maintenance import (
        MaintenanceAccessor as MaintenanceAccessor,
    )
    from dhis2w_client.v42.maintenance import (
        Notification as Notification,
    )
    from dhis2w_client.v42.maintenance import (
        NotificationDataType as NotificationDataType,
    )
    from dhis2w_client.v42.maintenance import (
        NotificationLevel as NotificationLevel,
    )
    from dhis2w_client.v42.maps import (
        LayerKind as LayerKind,
    )
    from dhis2w_client.v42.maps import (
        MapLayerSpec as MapLayerSpec,
    )
    from dhis2w_client.v42.maps import (
        MapsAccessor as MapsAccessor,
    )
    from dhis2w_client.v42.maps import (
        MapSpec as MapSpec,
    )
    from dhis2w_client.v42.messaging import (
        MessageConversation as MessageConversation,
    )
    from dhis2w_client.v42.messaging import (
        MessagingAccessor as MessagingAccessor,
    )
    from dhis2w_client.v42.messaging import (
        Recipient as Recipient,
    )
    from dhis2w_client.v42.metadata import (
        BulkPatchError as BulkPatchError,
    )
    from dhis2w_client.v42.metadata import (
        BulkPatchResult as BulkPatchResult,
    )
    from dhis2w_client.v42.metadata import (
        BulkSharingError as BulkSharingError,
    )
    from dhis2w_client.v42.metadata import (
        BulkSharingResult as BulkSharingResult,
    )
    from dhis2w_client.v42.metadata import (
        MetadataAccessor as MetadataAccessor,
    )
    from dhis2w_client.v42.metadata import (
        SearchHit as SearchHit,
    )
    from dhis2w_client.v42.metadata import (
        SearchResults as SearchResults,
    )
    from dhis2w_client.v42.option_sets import (
        OptionSetsAccessor as OptionSetsAccessor,
    )
    from dhis2w_client.v42.option_sets import (
        OptionSpec as OptionSpec,
    )
    from dhis2w_client.v42.option_sets import (
        UpsertReport as UpsertReport,
    )
    from dhis2w_client.v42.organisation_unit_group_sets import (
        OrganisationUnitGroupSet as OrganisationUnitGroupSet,
    )
    from dhis2w_client.v42.organisation_unit_group_sets import (
        OrganisationUnitGroupSetsAccessor as OrganisationUnitGroupSetsAccessor,
    )
    from dhis2w_client.v42.organisation_unit_groups import (
        OrganisationUnitGroup as OrganisationUnitGroup,
    )
    from dhis2w_client.v42.organisation_unit_groups import (
        OrganisationUnitGroupsAccessor as OrganisationUnitGroupsAccessor,
    )
    from dhis2w_client.v42.organisation_unit_levels import (
        OrganisationUnitLevel as OrganisationUnitLevel,
    )
    from dhis2w_client.v42.organisation_unit_levels import (
        OrganisationUnitLevelsAccessor as OrganisationUnitLevelsAccessor,
    )
    from dhis2w_client.v42.organisation_units import (
        OrganisationUnit as OrganisationUnit,
    )
    from dhis2w_client.v42.organisation_units import (
        OrganisationUnitsAccessor as OrganisationUnitsAccessor,
    )
    from dhis2w_client.v42.periods import (
        Period as Period,
    )
    from dhis2w_client.v42.periods import (
        PeriodKind as PeriodKind,
    )
    from dhis2w_client.v42.periods import (
        PeriodType as PeriodType,
    )
    from dhis2w_client.v42.periods import (
        RelativePeriod as RelativePeriod,
    )
    from dhis2w_client.v42.periods import (
        next_period_id as next_period_id,
    )
    from dhis2w_client.v42.periods import (
        parse_period as parse_period,
    )
    from dhis2w_client.v42.periods import (
        period_start_end as period_start_end,
    )
    from dhis2w_client.v42.periods import (
        previous_period_id as previous_period_id,
    )
    from dhis2w_client.v42.predictor_groups import (
        PredictorGroup as PredictorGroup,
    )
    from dhis2w_client.v42.predictor_groups import (
        PredictorGroupsAccessor as PredictorGroupsAccessor,
    )
    from dhis2w_client.v42.predictors import Predictor as Predictor
    from dhis2w_client.v42.predictors import PredictorsAccessor as PredictorsAccessor
    from dhis2w_client.v42.program_indicator_groups import (
        ProgramIndicatorGroup as ProgramIndicatorGroup,
    )
    from dhis2w_client.v42.program_indicator_groups import (
        ProgramIndicatorGroupsAccessor as ProgramIndicatorGroupsAccessor,
    )
    from dhis2w_client.v42.program_indicators import (
        ProgramIndicator as ProgramIndicator,
    )
    from dhis2w_client.v42.program_indicators import (
        ProgramIndicatorsAccessor as ProgramIndicatorsAccessor,
    )
    from dhis2w_client.v42.program_rules import ProgramRulesAccessor as ProgramRulesAccessor
    from dhis2w_client.v42.program_stages import (
        ProgramStage as ProgramStage,
    )
    from dhis2w_client.v42.program_stages import (
        ProgramStagesAccessor as ProgramStagesAccessor,
    )
    from dhis2w_client.v42.programs import Program as Program
    from dhis2w_client.v42.programs import ProgramsAccessor as ProgramsAccessor
    from dhis2w_client.v42.retry import RetryPolicy as RetryPolicy
    from dhis2w_client.v42.routes import RoutesAccessor as RoutesAccessor
    from dhis2w_client.v42.sections import Section as Section
    from dhis2w_client.v42.sections import SectionsAccessor as SectionsAccessor
    from dhis2w_client.v42.sharing import (
        ACCESS_NONE as ACCESS_NONE,
    )
    from dhis2w_client.v42.sharing import (
        ACCESS_READ_DATA as ACCESS_READ_DATA,
    )
    from dhis2w_client.v42.sharing import (
        ACCESS_READ_METADATA as ACCESS_READ_METADATA,
    )
    from dhis2w_client.v42.sharing import (
        ACCESS_READ_WRITE_DATA as ACCESS_READ_WRITE_DATA,
    )
    from dhis2w_client.v42.sharing import (
        ACCESS_READ_WRITE_METADATA as ACCESS_READ_WRITE_METADATA,
    )
    from dhis2w_client.v42.sharing import (
        Sharing as Sharing,
    )
    from dhis2w_client.v42.sharing import (
        SharingBuilder as SharingBuilder,
    )
    from dhis2w_client.v42.sharing import (
        SharingObject as SharingObject,
    )
    from dhis2w_client.v42.sharing import (
        access_string as access_string,
    )
    from dhis2w_client.v42.sharing import (
        apply_sharing as apply_sharing,
    )
    from dhis2w_client.v42.sharing import (
        get_sharing as get_sharing,
    )
    from dhis2w_client.v42.sql_views import (
        SqlViewColumn as SqlViewColumn,
    )
    from dhis2w_client.v42.sql_views import (
        SqlViewResult as SqlViewResult,
    )
    from dhis2w_client.v42.sql_views import (
        SqlViewRunner as SqlViewRunner,
    )
    from dhis2w_client.v42.sql_views import (
        SqlViewsAccessor as SqlViewsAccessor,
    )
    from dhis2w_client.v42.system import (
        DhisCalendar as DhisCalendar,
    )
    from dhis2w_client.v42.system import (
        DisplayRef as DisplayRef,
    )
    from dhis2w_client.v42.system import (
        Me as Me,
    )
    from dhis2w_client.v42.system import (
        SystemInfo as SystemInfo,
    )
    from dhis2w_client.v42.system import (
        SystemModule as SystemModule,
    )
    from dhis2w_client.v42.system_cache import SystemCache as SystemCache
    from dhis2w_client.v42.tasks import (
        TaskCompletion as TaskCompletion,
    )
    from dhis2w_client.v42.tasks import (
        TaskModule as TaskModule,
    )
    from dhis2w_client.v42.tasks import (
        TaskTimeoutError as TaskTimeoutError,
    )
    from dhis2w_client.v42.tasks import (
        parse_task_ref as parse_task_ref,
    )
    from dhis2w_client.v42.tracked_entity_attributes import (
        TrackedEntityAttribute as TrackedEntityAttribute,
    )
    from dhis2w_client.v42.tracked_entity_attributes import (
        TrackedEntityAttributesAccessor as TrackedEntityAttributesAccessor,
    )
    from dhis2w_client.v42.tracked_entity_types import (
        TrackedEntityType as TrackedEntityType,
    )
    from dhis2w_client.v42.tracked_entity_types import (
        TrackedEntityTypesAccessor as TrackedEntityTypesAccessor,
    )
    from dhis2w_client.v42.tracker import (
        EnrollResult as EnrollResult,
    )
    from dhis2w_client.v42.tracker import (
        EventResult as EventResult,
    )
    from dhis2w_client.v42.tracker import (
        OutstandingEnrollment as OutstandingEnrollment,
    )
    from dhis2w_client.v42.tracker import (
        RegisterResult as RegisterResult,
    )
    from dhis2w_client.v42.tracker import (
        TrackerAccessor as TrackerAccessor,
    )
    from dhis2w_client.v42.uids import (
        UID_ALPHABET as UID_ALPHABET,
    )
    from dhis2w_client.v42.uids import (
        UID_LENGTH as UID_LENGTH,
    )
    from dhis2w_client.v42.uids import (
        UID_LETTERS as UID_LETTERS,
    )
    from dhis2w_client.v42.uids import (
        UID_RE as UID_RE,
    )
    from dhis2w_client.v42.uids import (
        generate_uid as generate_uid,
    )
    from dhis2w_client.v42.uids import (
        generate_uids as generate_uids,
    )
    from dhis2w_client.v42.uids import (
        is_valid_uid as is_valid_uid,
    )
    from dhis2w_client.v42.validation import (
        ExpressionContext as ExpressionContext,
    )
    from dhis2w_client.v42.validation import (
        ExpressionDescription as ExpressionDescription,
    )
    from dhis2w_client.v42.validation import (
        ValidationAccessor as ValidationAccessor,
    )
    from dhis2w_client.v42.validation import (
        ValidationAnalysisResult as ValidationAnalysisResult,
    )
    from dhis2w_client.v42.validation_rule_groups import (
        ValidationRuleGroup as ValidationRuleGroup,
    )
    from dhis2w_client.v42.validation_rule_groups import (
        ValidationRuleGroupsAccessor as ValidationRuleGroupsAccessor,
    )
    from dhis2w_client.v42.validation_rules import (
        ValidationRule as ValidationRule,
    )
    from dhis2w_client.v42.validation_rules import (
        ValidationRulesAccessor as ValidationRulesAccessor,
    )
    from dhis2w_client.v42.visualizations import (
        DimensionAxis as DimensionAxis,
    )
    from dhis2w_client.v42.visualizations import (
        VisualizationsAccessor as VisualizationsAccessor,
    )
    from dhis2w_client.v42.visualizations import (
        VisualizationSpec as VisualizationSpec,
    )


__all__ = [
    "ACCESS_NONE",
    "ACCESS_READ_DATA",
    "ACCESS_READ_METADATA",
    "ACCESS_READ_WRITE_DATA",
    "ACCESS_READ_WRITE_METADATA",
    "AddOp",
    "AnalyticsAccessor",
    "AnalyticsMetaData",
    "ApiHeadersAuthScheme",
    "ApiQueryParamsAuthScheme",
    "ApiTokenAuthScheme",
    "App",
    "AppHubApp",
    "AppHubVersion",
    "AppSnapshotEntry",
    "AppStatus",
    "AppType",
    "AppsAccessor",
    "AppsSnapshot",
    "AttributeValuesAccessor",
    "AuthProvider",
    "AuthScheme",
    "AuthSchemeAdapter",
    "AuthenticationError",
    "BasicAuth",
    "BulkPatchError",
    "BulkPatchResult",
    "BulkSharingError",
    "BulkSharingResult",
    "CategoriesAccessor",
    "Category",
    "CategoryBuildEntry",
    "CategoryCombo",
    "CategoryComboBuildResult",
    "CategoryComboBuildSpec",
    "CategoryCombosAccessor",
    "CategoryOption",
    "CategoryOptionCombo",
    "CategoryOptionCombosAccessor",
    "CategoryOptionGroup",
    "CategoryOptionSpec",
    "CategorySpec",
    "CategoryOptionGroupSet",
    "CategoryOptionGroupSetsAccessor",
    "CategoryOptionGroupsAccessor",
    "CategoryOptionsAccessor",
    "Conflict",
    "ConflictRow",
    "CopyOp",
    "CustomizationResult",
    "CustomizeAccessor",
    "DashboardSlot",
    "DashboardsAccessor",
    "DataElement",
    "DataElementGroup",
    "DataElementGroupSet",
    "DataElementGroupSetsAccessor",
    "DataElementGroupsAccessor",
    "DataElementsAccessor",
    "DataIntegrityCheck",
    "DataIntegrityIssue",
    "DataIntegrityReport",
    "DataIntegrityResult",
    "DataSet",
    "DataSetsAccessor",
    "DataValue",
    "DataValueSet",
    "DataValuesAccessor",
    "DatastoreAccessor",
    "Dhis2",
    "Dhis2ApiError",
    "Dhis2Client",
    "Dhis2ClientError",
    "DhisCalendar",
    "DimensionAxis",
    "DisplayRef",
    "Document",
    "EnrollResult",
    "ErrorReport",
    "EventResult",
    "ExpressionContext",
    "ExpressionDescription",
    "FileResource",
    "FileResourceDomain",
    "FilesAccessor",
    "Grid",
    "GridHeader",
    "HttpBasicAuthScheme",
    "ImportCount",
    "ImportReport",
    "Indicator",
    "IndicatorGroup",
    "IndicatorGroupSet",
    "IndicatorGroupSetsAccessor",
    "IndicatorGroupsAccessor",
    "IndicatorsAccessor",
    "IntegrityIssueRow",
    "InvalidProfileNameError",
    "JobType",
    "JsonPatchOp",
    "JsonPatchOpAdapter",
    "LayerKind",
    "Legend",
    "LegendSet",
    "LegendSetSpec",
    "LegendSetsAccessor",
    "LegendSpec",
    "LoginCustomization",
    "MaintenanceAccessor",
    "MapLayerSpec",
    "MapSpec",
    "MapsAccessor",
    "Me",
    "MessageConversation",
    "MessagingAccessor",
    "MetadataAccessor",
    "MoveOp",
    "NoProfileError",
    "Notification",
    "NotificationDataType",
    "NotificationLevel",
    "OAuth2Auth",
    "OAuth2ClientCredentialsAuthScheme",
    "OAuth2FlowError",
    "OAuth2Token",
    "ObjectReport",
    "OptionSetsAccessor",
    "OptionSpec",
    "OrganisationUnit",
    "OrganisationUnitGroup",
    "OrganisationUnitGroupSet",
    "OrganisationUnitGroupSetsAccessor",
    "OrganisationUnitGroupsAccessor",
    "OrganisationUnitLevel",
    "OrganisationUnitLevelsAccessor",
    "OrganisationUnitsAccessor",
    "OutstandingEnrollment",
    "PROFILE_NAME_MAX_LEN",
    "PatAuth",
    "Period",
    "PeriodKind",
    "PeriodType",
    "Predictor",
    "PredictorGroup",
    "PredictorGroupsAccessor",
    "PredictorsAccessor",
    "Profile",
    "ProgramIndicator",
    "ProgramIndicatorGroup",
    "ProgramIndicatorGroupsAccessor",
    "ProgramIndicatorsAccessor",
    "Program",
    "ProgramRulesAccessor",
    "ProgramStage",
    "ProgramStagesAccessor",
    "ProgramsAccessor",
    "Recipient",
    "RegisterResult",
    "RelativePeriod",
    "RestoreOutcome",
    "RestoreSummary",
    "RemoveOp",
    "ReplaceOp",
    "RetryPolicy",
    "RoutesAccessor",
    "SearchHit",
    "SearchResults",
    "Section",
    "SectionsAccessor",
    "Sharing",
    "SharingBuilder",
    "SharingObject",
    "SqlViewColumn",
    "SqlViewResult",
    "SqlViewRunner",
    "SqlViewsAccessor",
    "Stats",
    "SystemCache",
    "SystemInfo",
    "SystemModule",
    "TaskCompletion",
    "TaskModule",
    "TaskTimeoutError",
    "TestOp",
    "TokenStore",
    "TrackedEntityAttribute",
    "TrackedEntityAttributesAccessor",
    "TrackedEntityType",
    "TrackedEntityTypesAccessor",
    "TrackerAccessor",
    "TypeReport",
    "UID_ALPHABET",
    "UID_LENGTH",
    "UID_LETTERS",
    "UID_RE",
    "UnknownProfileError",
    "UnsupportedVersionError",
    "UpsertReport",
    "ValidationAccessor",
    "ValidationAnalysisResult",
    "ValidationRule",
    "ValidationRuleGroup",
    "ValidationRuleGroupsAccessor",
    "ValidationRulesAccessor",
    "VisualizationSpec",
    "VisualizationsAccessor",
    "WebMessageResponse",
    "access_string",
    "apply_sharing",
    "auth_scheme_from_route",
    "build_auth_for_basic",
    "build_category_combo",
    "generate_uid",
    "generate_uids",
    "get_sharing",
    "is_valid_uid",
    "next_period_id",
    "open_client",
    "parse_period",
    "parse_task_ref",
    "period_start_end",
    "previous_period_id",
    "profile_from_env_raw",
    "validate_profile_name",
]

_LAZY_EXPORTS: dict[str, str] = {
    "ACCESS_NONE": "dhis2w_client.v42.sharing",
    "ACCESS_READ_DATA": "dhis2w_client.v42.sharing",
    "ACCESS_READ_METADATA": "dhis2w_client.v42.sharing",
    "ACCESS_READ_WRITE_DATA": "dhis2w_client.v42.sharing",
    "ACCESS_READ_WRITE_METADATA": "dhis2w_client.v42.sharing",
    "AddOp": "dhis2w_client.v42.json_patch",
    "AnalyticsAccessor": "dhis2w_client.v42.analytics_stream",
    "AnalyticsMetaData": "dhis2w_client.v42.analytics",
    "ApiHeadersAuthScheme": "dhis2w_client.v42.auth_schemes",
    "ApiQueryParamsAuthScheme": "dhis2w_client.v42.auth_schemes",
    "ApiTokenAuthScheme": "dhis2w_client.v42.auth_schemes",
    "App": "dhis2w_client.v42.apps",
    "AppHubApp": "dhis2w_client.v42.apps",
    "AppHubVersion": "dhis2w_client.v42.apps",
    "AppSnapshotEntry": "dhis2w_client.v42.apps",
    "AppStatus": "dhis2w_client.v42.apps",
    "AppType": "dhis2w_client.v42.apps",
    "AppsAccessor": "dhis2w_client.v42.apps",
    "AppsSnapshot": "dhis2w_client.v42.apps",
    "AttributeValuesAccessor": "dhis2w_client.v42.attribute_values",
    "AuthProvider": "dhis2w_client.v42.auth.base",
    "AuthScheme": "dhis2w_client.v42.auth_schemes",
    "AuthSchemeAdapter": "dhis2w_client.v42.auth_schemes",
    "AuthenticationError": "dhis2w_client.errors",
    "BasicAuth": "dhis2w_client.v42.auth.basic",
    "BulkPatchError": "dhis2w_client.v42.metadata",
    "BulkPatchResult": "dhis2w_client.v42.metadata",
    "BulkSharingError": "dhis2w_client.v42.metadata",
    "BulkSharingResult": "dhis2w_client.v42.metadata",
    "CategoriesAccessor": "dhis2w_client.v42.categories",
    "Category": "dhis2w_client.v42.categories",
    "CategoryBuildEntry": "dhis2w_client.v42.category_combo_builder",
    "CategoryCombo": "dhis2w_client.v42.category_combos",
    "CategoryComboBuildResult": "dhis2w_client.v42.category_combo_builder",
    "CategoryComboBuildSpec": "dhis2w_client.v42.category_combo_builder",
    "CategoryCombosAccessor": "dhis2w_client.v42.category_combos",
    "CategoryOption": "dhis2w_client.v42.category_options",
    "CategoryOptionCombo": "dhis2w_client.v42.category_option_combos",
    "CategoryOptionCombosAccessor": "dhis2w_client.v42.category_option_combos",
    "CategoryOptionGroup": "dhis2w_client.v42.category_option_groups",
    "CategoryOptionSpec": "dhis2w_client.v42.category_combo_builder",
    "CategorySpec": "dhis2w_client.v42.category_combo_builder",
    "CategoryOptionGroupSet": "dhis2w_client.v42.category_option_group_sets",
    "CategoryOptionGroupSetsAccessor": "dhis2w_client.v42.category_option_group_sets",
    "CategoryOptionGroupsAccessor": "dhis2w_client.v42.category_option_groups",
    "CategoryOptionsAccessor": "dhis2w_client.v42.category_options",
    "Conflict": "dhis2w_client.v42.envelopes",
    "ConflictRow": "dhis2w_client.v42.envelopes",
    "CopyOp": "dhis2w_client.v42.json_patch",
    "CustomizationResult": "dhis2w_client.v42.customize",
    "CustomizeAccessor": "dhis2w_client.v42.customize",
    "DashboardSlot": "dhis2w_client.v42.dashboards",
    "DashboardsAccessor": "dhis2w_client.v42.dashboards",
    "DataElement": "dhis2w_client.v42.data_elements",
    "DataElementGroup": "dhis2w_client.v42.data_element_groups",
    "DataElementGroupSet": "dhis2w_client.v42.data_element_group_sets",
    "DataElementGroupSetsAccessor": "dhis2w_client.v42.data_element_group_sets",
    "DataElementGroupsAccessor": "dhis2w_client.v42.data_element_groups",
    "DataElementsAccessor": "dhis2w_client.v42.data_elements",
    "DataIntegrityCheck": "dhis2w_client.v42.maintenance",
    "DataIntegrityIssue": "dhis2w_client.v42.maintenance",
    "DataIntegrityReport": "dhis2w_client.v42.maintenance",
    "DataIntegrityResult": "dhis2w_client.v42.maintenance",
    "DataSet": "dhis2w_client.v42.data_sets",
    "DataSetsAccessor": "dhis2w_client.v42.data_sets",
    "DataValue": "dhis2w_client.v42.aggregate",
    "DataValueSet": "dhis2w_client.v42.aggregate",
    "DataValuesAccessor": "dhis2w_client.v42.data_values",
    "DatastoreAccessor": "dhis2w_client.v42.datastore",
    "Dhis2": "dhis2w_client.generated",
    "Dhis2ApiError": "dhis2w_client.errors",
    "Dhis2Client": "dhis2w_client.v42.client",
    "Dhis2ClientError": "dhis2w_client.errors",
    "DhisCalendar": "dhis2w_client.v42.system",
    "DimensionAxis": "dhis2w_client.v42.visualizations",
    "DisplayRef": "dhis2w_client.v42.system",
    "Document": "dhis2w_client.v42.files",
    "EnrollResult": "dhis2w_client.v42.tracker",
    "ErrorReport": "dhis2w_client.v42.envelopes",
    "EventResult": "dhis2w_client.v42.tracker",
    "ExpressionContext": "dhis2w_client.v42.validation",
    "ExpressionDescription": "dhis2w_client.v42.validation",
    "FileResource": "dhis2w_client.v42.files",
    "FileResourceDomain": "dhis2w_client.v42.files",
    "FilesAccessor": "dhis2w_client.v42.files",
    "Grid": "dhis2w_client.v42.analytics",
    "GridHeader": "dhis2w_client.v42.analytics",
    "HttpBasicAuthScheme": "dhis2w_client.v42.auth_schemes",
    "ImportCount": "dhis2w_client.v42.envelopes",
    "ImportReport": "dhis2w_client.v42.envelopes",
    "Indicator": "dhis2w_client.v42.indicators",
    "IndicatorGroup": "dhis2w_client.v42.indicator_groups",
    "IndicatorGroupSet": "dhis2w_client.v42.indicator_group_sets",
    "IndicatorGroupSetsAccessor": "dhis2w_client.v42.indicator_group_sets",
    "IndicatorGroupsAccessor": "dhis2w_client.v42.indicator_groups",
    "IndicatorsAccessor": "dhis2w_client.v42.indicators",
    "IntegrityIssueRow": "dhis2w_client.v42.maintenance",
    "InvalidProfileNameError": "dhis2w_client.profile",
    "JobType": "dhis2w_client.v42.maintenance",
    "JsonPatchOp": "dhis2w_client.v42.json_patch",
    "JsonPatchOpAdapter": "dhis2w_client.v42.json_patch",
    "LayerKind": "dhis2w_client.v42.maps",
    "Legend": "dhis2w_client.v42.legend_sets",
    "LegendSet": "dhis2w_client.v42.legend_sets",
    "LegendSetSpec": "dhis2w_client.v42.legend_sets",
    "LegendSetsAccessor": "dhis2w_client.v42.legend_sets",
    "LegendSpec": "dhis2w_client.v42.legend_sets",
    "LoginCustomization": "dhis2w_client.v42.customize",
    "MaintenanceAccessor": "dhis2w_client.v42.maintenance",
    "MapLayerSpec": "dhis2w_client.v42.maps",
    "MapSpec": "dhis2w_client.v42.maps",
    "MapsAccessor": "dhis2w_client.v42.maps",
    "Me": "dhis2w_client.v42.system",
    "MessageConversation": "dhis2w_client.v42.messaging",
    "MessagingAccessor": "dhis2w_client.v42.messaging",
    "MetadataAccessor": "dhis2w_client.v42.metadata",
    "MoveOp": "dhis2w_client.v42.json_patch",
    "NoProfileError": "dhis2w_client.profile",
    "Notification": "dhis2w_client.v42.maintenance",
    "NotificationDataType": "dhis2w_client.v42.maintenance",
    "NotificationLevel": "dhis2w_client.v42.maintenance",
    "OAuth2Auth": "dhis2w_client.v42.auth.oauth2",
    "OAuth2ClientCredentialsAuthScheme": "dhis2w_client.v42.auth_schemes",
    "OAuth2FlowError": "dhis2w_client.errors",
    "OAuth2Token": "dhis2w_client.v42.auth.oauth2",
    "ObjectReport": "dhis2w_client.v42.envelopes",
    "OptionSetsAccessor": "dhis2w_client.v42.option_sets",
    "OptionSpec": "dhis2w_client.v42.option_sets",
    "OrganisationUnit": "dhis2w_client.v42.organisation_units",
    "OrganisationUnitGroup": "dhis2w_client.v42.organisation_unit_groups",
    "OrganisationUnitGroupSet": "dhis2w_client.v42.organisation_unit_group_sets",
    "OrganisationUnitGroupSetsAccessor": "dhis2w_client.v42.organisation_unit_group_sets",
    "OrganisationUnitGroupsAccessor": "dhis2w_client.v42.organisation_unit_groups",
    "OrganisationUnitLevel": "dhis2w_client.v42.organisation_unit_levels",
    "OrganisationUnitLevelsAccessor": "dhis2w_client.v42.organisation_unit_levels",
    "OrganisationUnitsAccessor": "dhis2w_client.v42.organisation_units",
    "OutstandingEnrollment": "dhis2w_client.v42.tracker",
    "PROFILE_NAME_MAX_LEN": "dhis2w_client.profile",
    "PatAuth": "dhis2w_client.v42.auth.pat",
    "Period": "dhis2w_client.v42.periods",
    "PeriodKind": "dhis2w_client.v42.periods",
    "PeriodType": "dhis2w_client.v42.periods",
    "Predictor": "dhis2w_client.v42.predictors",
    "PredictorGroup": "dhis2w_client.v42.predictor_groups",
    "PredictorGroupsAccessor": "dhis2w_client.v42.predictor_groups",
    "PredictorsAccessor": "dhis2w_client.v42.predictors",
    "Profile": "dhis2w_client.profile",
    "ProgramIndicator": "dhis2w_client.v42.program_indicators",
    "ProgramIndicatorGroup": "dhis2w_client.v42.program_indicator_groups",
    "ProgramIndicatorGroupsAccessor": "dhis2w_client.v42.program_indicator_groups",
    "ProgramIndicatorsAccessor": "dhis2w_client.v42.program_indicators",
    "Program": "dhis2w_client.v42.programs",
    "ProgramRulesAccessor": "dhis2w_client.v42.program_rules",
    "ProgramStage": "dhis2w_client.v42.program_stages",
    "ProgramStagesAccessor": "dhis2w_client.v42.program_stages",
    "ProgramsAccessor": "dhis2w_client.v42.programs",
    "Recipient": "dhis2w_client.v42.messaging",
    "RegisterResult": "dhis2w_client.v42.tracker",
    "RelativePeriod": "dhis2w_client.v42.periods",
    "RestoreOutcome": "dhis2w_client.v42.apps",
    "RestoreSummary": "dhis2w_client.v42.apps",
    "RemoveOp": "dhis2w_client.v42.json_patch",
    "ReplaceOp": "dhis2w_client.v42.json_patch",
    "RetryPolicy": "dhis2w_client.v42.retry",
    "RoutesAccessor": "dhis2w_client.v42.routes",
    "SearchHit": "dhis2w_client.v42.metadata",
    "SearchResults": "dhis2w_client.v42.metadata",
    "Section": "dhis2w_client.v42.sections",
    "SectionsAccessor": "dhis2w_client.v42.sections",
    "Sharing": "dhis2w_client.v42.sharing",
    "SharingBuilder": "dhis2w_client.v42.sharing",
    "SharingObject": "dhis2w_client.v42.sharing",
    "SqlViewColumn": "dhis2w_client.v42.sql_views",
    "SqlViewResult": "dhis2w_client.v42.sql_views",
    "SqlViewRunner": "dhis2w_client.v42.sql_views",
    "SqlViewsAccessor": "dhis2w_client.v42.sql_views",
    "Stats": "dhis2w_client.v42.envelopes",
    "SystemCache": "dhis2w_client.v42.system_cache",
    "SystemInfo": "dhis2w_client.v42.system",
    "SystemModule": "dhis2w_client.v42.system",
    "TaskCompletion": "dhis2w_client.v42.tasks",
    "TaskModule": "dhis2w_client.v42.tasks",
    "TaskTimeoutError": "dhis2w_client.v42.tasks",
    "TestOp": "dhis2w_client.v42.json_patch",
    "TokenStore": "dhis2w_client.v42.auth.oauth2",
    "TrackedEntityAttribute": "dhis2w_client.v42.tracked_entity_attributes",
    "TrackedEntityAttributesAccessor": "dhis2w_client.v42.tracked_entity_attributes",
    "TrackedEntityType": "dhis2w_client.v42.tracked_entity_types",
    "TrackedEntityTypesAccessor": "dhis2w_client.v42.tracked_entity_types",
    "TrackerAccessor": "dhis2w_client.v42.tracker",
    "TypeReport": "dhis2w_client.v42.envelopes",
    "UID_ALPHABET": "dhis2w_client.v42.uids",
    "UID_LENGTH": "dhis2w_client.v42.uids",
    "UID_LETTERS": "dhis2w_client.v42.uids",
    "UID_RE": "dhis2w_client.v42.uids",
    "UnknownProfileError": "dhis2w_client.profile",
    "UnsupportedVersionError": "dhis2w_client.errors",
    "UpsertReport": "dhis2w_client.v42.option_sets",
    "ValidationAccessor": "dhis2w_client.v42.validation",
    "ValidationAnalysisResult": "dhis2w_client.v42.validation",
    "ValidationRule": "dhis2w_client.v42.validation_rules",
    "ValidationRuleGroup": "dhis2w_client.v42.validation_rule_groups",
    "ValidationRuleGroupsAccessor": "dhis2w_client.v42.validation_rule_groups",
    "ValidationRulesAccessor": "dhis2w_client.v42.validation_rules",
    "VisualizationSpec": "dhis2w_client.v42.visualizations",
    "VisualizationsAccessor": "dhis2w_client.v42.visualizations",
    "WebMessageResponse": "dhis2w_client.v42.envelopes",
    "access_string": "dhis2w_client.v42.sharing",
    "apply_sharing": "dhis2w_client.v42.sharing",
    "auth_scheme_from_route": "dhis2w_client.v42.auth_schemes",
    "build_auth_for_basic": "dhis2w_client.v42.client_context",
    "build_category_combo": "dhis2w_client.v42.category_combo_builder",
    "generate_uid": "dhis2w_client.v42.uids",
    "generate_uids": "dhis2w_client.v42.uids",
    "get_sharing": "dhis2w_client.v42.sharing",
    "is_valid_uid": "dhis2w_client.v42.uids",
    "next_period_id": "dhis2w_client.v42.periods",
    "open_client": "dhis2w_client.v42.client_context",
    "parse_period": "dhis2w_client.v42.periods",
    "parse_task_ref": "dhis2w_client.v42.tasks",
    "period_start_end": "dhis2w_client.v42.periods",
    "previous_period_id": "dhis2w_client.v42.periods",
    "profile_from_env_raw": "dhis2w_client.profile",
    "validate_profile_name": "dhis2w_client.profile",
}


def __getattr__(name: str) -> object:
    """Resolve a public symbol to its module on first access (PEP 562)."""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_path), name)


def __dir__() -> list[str]:
    """Expose the full public surface to tab-completion + dir()."""
    return sorted(__all__)
