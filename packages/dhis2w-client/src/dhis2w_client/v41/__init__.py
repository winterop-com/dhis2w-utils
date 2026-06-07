"""DHIS2 v41 client surface — re-exports the v41 hand-written tree."""

from dhis2w_client.errors import (
    AuthenticationError,
    Dhis2ApiError,
    Dhis2ClientError,
    OAuth2FlowError,
    UnsupportedVersionError,
)
from dhis2w_client.generated import Dhis2
from dhis2w_client.profile import (
    PROFILE_NAME_MAX_LEN,
    InvalidProfileNameError,
    NoProfileError,
    Profile,
    UnknownProfileError,
    profile_from_env_raw,
    validate_profile_name,
)
from dhis2w_client.v41.aggregate import DataValue, DataValueSet
from dhis2w_client.v41.analytics import AnalyticsMetaData, Grid, GridHeader
from dhis2w_client.v41.analytics_stream import AnalyticsAccessor
from dhis2w_client.v41.apps import (
    App,
    AppHubApp,
    AppHubVersion,
    AppsAccessor,
    AppSnapshotEntry,
    AppsSnapshot,
    AppStatus,
    AppType,
    RestoreOutcome,
    RestoreSummary,
)
from dhis2w_client.v41.attribute_values import AttributeValuesAccessor
from dhis2w_client.v41.auth.base import AuthProvider
from dhis2w_client.v41.auth.basic import BasicAuth
from dhis2w_client.v41.auth.oauth2 import OAuth2Auth, OAuth2Token, TokenStore
from dhis2w_client.v41.auth.pat import PatAuth
from dhis2w_client.v41.auth_schemes import (
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    ApiTokenAuthScheme,
    AuthScheme,
    AuthSchemeAdapter,
    HttpBasicAuthScheme,
    auth_scheme_from_route,
)
from dhis2w_client.v41.categories import CategoriesAccessor, Category
from dhis2w_client.v41.category_combo_builder import (
    CategoryBuildEntry,
    CategoryComboBuildResult,
    CategoryComboBuildSpec,
    CategoryOptionSpec,
    CategorySpec,
    build_category_combo,
)
from dhis2w_client.v41.category_combos import CategoryCombo, CategoryCombosAccessor
from dhis2w_client.v41.category_option_combos import CategoryOptionCombo, CategoryOptionCombosAccessor
from dhis2w_client.v41.category_option_group_sets import CategoryOptionGroupSet, CategoryOptionGroupSetsAccessor
from dhis2w_client.v41.category_option_groups import CategoryOptionGroup, CategoryOptionGroupsAccessor
from dhis2w_client.v41.category_options import CategoryOption, CategoryOptionsAccessor
from dhis2w_client.v41.client import Dhis2Client
from dhis2w_client.v41.client_context import build_auth_for_basic, open_client
from dhis2w_client.v41.customize import CustomizationResult, CustomizeAccessor, LoginCustomization
from dhis2w_client.v41.dashboards import DashboardsAccessor, DashboardSlot
from dhis2w_client.v41.data_element_group_sets import DataElementGroupSet, DataElementGroupSetsAccessor
from dhis2w_client.v41.data_element_groups import DataElementGroup, DataElementGroupsAccessor
from dhis2w_client.v41.data_elements import DataElement, DataElementsAccessor
from dhis2w_client.v41.data_sets import DataSet, DataSetsAccessor
from dhis2w_client.v41.data_values import DataValuesAccessor
from dhis2w_client.v41.envelopes import (
    Conflict,
    ConflictRow,
    ErrorReport,
    ImportCount,
    ImportReport,
    ObjectReport,
    Stats,
    TypeReport,
    WebMessageResponse,
)
from dhis2w_client.v41.files import Document, FileResource, FileResourceDomain, FilesAccessor
from dhis2w_client.v41.indicator_group_sets import IndicatorGroupSet, IndicatorGroupSetsAccessor
from dhis2w_client.v41.indicator_groups import IndicatorGroup, IndicatorGroupsAccessor
from dhis2w_client.v41.indicators import Indicator, IndicatorsAccessor
from dhis2w_client.v41.json_patch import (
    AddOp,
    CopyOp,
    JsonPatchOp,
    JsonPatchOpAdapter,
    MoveOp,
    RemoveOp,
    ReplaceOp,
    TestOp,
)
from dhis2w_client.v41.legend_sets import (
    Legend,
    LegendSet,
    LegendSetsAccessor,
    LegendSetSpec,
    LegendSpec,
)
from dhis2w_client.v41.maintenance import (
    DataIntegrityCheck,
    DataIntegrityIssue,
    DataIntegrityReport,
    DataIntegrityResult,
    IntegrityIssueRow,
    JobType,
    MaintenanceAccessor,
    Notification,
    NotificationDataType,
    NotificationLevel,
)
from dhis2w_client.v41.maps import LayerKind, MapLayerSpec, MapsAccessor, MapSpec
from dhis2w_client.v41.messaging import MessageConversation, MessagingAccessor, Recipient
from dhis2w_client.v41.metadata import (
    BulkPatchError,
    BulkPatchResult,
    BulkSharingError,
    BulkSharingResult,
    MetadataAccessor,
    SearchHit,
    SearchResults,
)
from dhis2w_client.v41.option_sets import OptionSetsAccessor, OptionSpec, UpsertReport
from dhis2w_client.v41.organisation_unit_group_sets import (
    OrganisationUnitGroupSet,
    OrganisationUnitGroupSetsAccessor,
)
from dhis2w_client.v41.organisation_unit_groups import OrganisationUnitGroup, OrganisationUnitGroupsAccessor
from dhis2w_client.v41.organisation_unit_levels import OrganisationUnitLevel, OrganisationUnitLevelsAccessor
from dhis2w_client.v41.organisation_units import OrganisationUnit, OrganisationUnitsAccessor
from dhis2w_client.v41.periods import (
    Period,
    PeriodKind,
    PeriodType,
    RelativePeriod,
    next_period_id,
    parse_period,
    period_start_end,
    previous_period_id,
)
from dhis2w_client.v41.predictor_groups import PredictorGroup, PredictorGroupsAccessor
from dhis2w_client.v41.predictors import Predictor, PredictorsAccessor
from dhis2w_client.v41.program_indicator_groups import ProgramIndicatorGroup, ProgramIndicatorGroupsAccessor
from dhis2w_client.v41.program_indicators import ProgramIndicator, ProgramIndicatorsAccessor
from dhis2w_client.v41.program_rules import ProgramRulesAccessor
from dhis2w_client.v41.program_stages import ProgramStage, ProgramStagesAccessor
from dhis2w_client.v41.programs import Program, ProgramsAccessor
from dhis2w_client.v41.retry import RetryPolicy
from dhis2w_client.v41.sections import Section, SectionsAccessor
from dhis2w_client.v41.sharing import (
    ACCESS_NONE,
    ACCESS_READ_DATA,
    ACCESS_READ_METADATA,
    ACCESS_READ_WRITE_DATA,
    ACCESS_READ_WRITE_METADATA,
    Sharing,
    SharingBuilder,
    SharingObject,
    access_string,
    apply_sharing,
    get_sharing,
)
from dhis2w_client.v41.sql_views import (
    SqlViewColumn,
    SqlViewResult,
    SqlViewRunner,
    SqlViewsAccessor,
)
from dhis2w_client.v41.system import DhisCalendar, DisplayRef, Me, SystemInfo, SystemModule
from dhis2w_client.v41.system_cache import SystemCache
from dhis2w_client.v41.tasks import TaskCompletion, TaskModule, TaskTimeoutError, parse_task_ref
from dhis2w_client.v41.tracked_entity_attributes import TrackedEntityAttribute, TrackedEntityAttributesAccessor
from dhis2w_client.v41.tracked_entity_types import TrackedEntityType, TrackedEntityTypesAccessor
from dhis2w_client.v41.tracker import (
    EnrollResult,
    EventResult,
    OutstandingEnrollment,
    RegisterResult,
    TrackerAccessor,
)
from dhis2w_client.v41.uids import (
    UID_ALPHABET,
    UID_LENGTH,
    UID_LETTERS,
    UID_RE,
    generate_uid,
    generate_uids,
    is_valid_uid,
)
from dhis2w_client.v41.validation import (
    ExpressionContext,
    ExpressionDescription,
    ValidationAccessor,
    ValidationAnalysisResult,
)
from dhis2w_client.v41.validation_rule_groups import ValidationRuleGroup, ValidationRuleGroupsAccessor
from dhis2w_client.v41.validation_rules import ValidationRule, ValidationRulesAccessor
from dhis2w_client.v41.visualizations import DimensionAxis, VisualizationsAccessor, VisualizationSpec

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
