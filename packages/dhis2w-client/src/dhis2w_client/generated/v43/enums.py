"""Generated DHIS2 v43 StrEnums. Do not edit by hand."""

from __future__ import annotations

from enum import StrEnum

# Hand-written enums that DHIS2's /api/schemas doesn't expose as CONSTANT
# (class-hierarchy types like PeriodType). Re-exported here so generated
# schema modules have a single import path for every enum.
from dhis2w_client.v43.periods import PeriodType as PeriodType


class AccessLevel(StrEnum):
    """org.hisp.dhis.common.AccessLevel (DHIS2 v43)."""

    OPEN = "OPEN"
    AUDITED = "AUDITED"
    PROTECTED = "PROTECTED"
    CLOSED = "CLOSED"


class AggregationType(StrEnum):
    """org.hisp.dhis.analytics.AggregationType (DHIS2 v43)."""

    SUM = "SUM"
    AVERAGE = "AVERAGE"
    AVERAGE_SUM_ORG_UNIT = "AVERAGE_SUM_ORG_UNIT"
    LAST = "LAST"
    LAST_AVERAGE_ORG_UNIT = "LAST_AVERAGE_ORG_UNIT"
    LAST_LAST_ORG_UNIT = "LAST_LAST_ORG_UNIT"
    LAST_IN_PERIOD = "LAST_IN_PERIOD"
    LAST_IN_PERIOD_AVERAGE_ORG_UNIT = "LAST_IN_PERIOD_AVERAGE_ORG_UNIT"
    FIRST = "FIRST"
    FIRST_AVERAGE_ORG_UNIT = "FIRST_AVERAGE_ORG_UNIT"
    FIRST_FIRST_ORG_UNIT = "FIRST_FIRST_ORG_UNIT"
    COUNT = "COUNT"
    STDDEV = "STDDEV"
    VARIANCE = "VARIANCE"
    MIN = "MIN"
    MAX = "MAX"
    MIN_SUM_ORG_UNIT = "MIN_SUM_ORG_UNIT"
    MAX_SUM_ORG_UNIT = "MAX_SUM_ORG_UNIT"
    NONE = "NONE"
    CUSTOM = "CUSTOM"
    DEFAULT = "DEFAULT"


class AnalyticsFavoriteType(StrEnum):
    """org.hisp.dhis.analytics.AnalyticsFavoriteType (DHIS2 v43)."""

    VISUALIZATION = "VISUALIZATION"
    EVENT_VISUALIZATION = "EVENT_VISUALIZATION"
    MAP = "MAP"
    EVENT_REPORT = "EVENT_REPORT"
    EVENT_CHART = "EVENT_CHART"
    DATASET_REPORT = "DATASET_REPORT"


class AnalyticsPeriodBoundaryType(StrEnum):
    """org.hisp.dhis.program.AnalyticsPeriodBoundaryType (DHIS2 v43)."""

    BEFORE_START_OF_REPORTING_PERIOD = "BEFORE_START_OF_REPORTING_PERIOD"
    BEFORE_END_OF_REPORTING_PERIOD = "BEFORE_END_OF_REPORTING_PERIOD"
    AFTER_START_OF_REPORTING_PERIOD = "AFTER_START_OF_REPORTING_PERIOD"
    AFTER_END_OF_REPORTING_PERIOD = "AFTER_END_OF_REPORTING_PERIOD"


class AnalyticsTablePhase(StrEnum):
    """org.hisp.dhis.analytics.AnalyticsTablePhase (DHIS2 v43)."""

    RESOURCE_TABLE_POPULATED = "RESOURCE_TABLE_POPULATED"
    ANALYTICS_TABLE_POPULATED = "ANALYTICS_TABLE_POPULATED"


class AnalyticsTableType(StrEnum):
    """org.hisp.dhis.analytics.AnalyticsTableType (DHIS2 v43)."""

    DATA_VALUE = "DATA_VALUE"
    COMPLETENESS = "COMPLETENESS"
    COMPLETENESS_TARGET = "COMPLETENESS_TARGET"
    ORG_UNIT_TARGET = "ORG_UNIT_TARGET"
    VALIDATION_RESULT = "VALIDATION_RESULT"
    EVENT = "EVENT"
    ENROLLMENT = "ENROLLMENT"
    OWNERSHIP = "OWNERSHIP"
    TRACKED_ENTITY_INSTANCE_EVENTS = "TRACKED_ENTITY_INSTANCE_EVENTS"
    TRACKED_ENTITY_INSTANCE_ENROLLMENTS = "TRACKED_ENTITY_INSTANCE_ENROLLMENTS"
    TRACKED_ENTITY_INSTANCE = "TRACKED_ENTITY_INSTANCE"


class AnalyticsType(StrEnum):
    """org.hisp.dhis.program.AnalyticsType (DHIS2 v43)."""

    EVENT = "EVENT"
    ENROLLMENT = "ENROLLMENT"


class ApiTokenType(StrEnum):
    """org.hisp.dhis.security.apikey.ApiTokenType (DHIS2 v43)."""

    PERSONAL_ACCESS_TOKEN_V1 = "PERSONAL_ACCESS_TOKEN_V1"
    PERSONAL_ACCESS_TOKEN_V2 = "PERSONAL_ACCESS_TOKEN_V2"


class Attribute(StrEnum):
    """org.hisp.dhis.eventvisualization.Attribute (DHIS2 v43)."""

    COLUMN = "COLUMN"
    ROW = "ROW"
    FILTER = "FILTER"


class CacheStrategy(StrEnum):
    """org.hisp.dhis.common.cache.CacheStrategy (DHIS2 v43)."""

    NO_CACHE = "NO_CACHE"
    CACHE_1_MINUTE = "CACHE_1_MINUTE"
    CACHE_5_MINUTES = "CACHE_5_MINUTES"
    CACHE_10_MINUTES = "CACHE_10_MINUTES"
    CACHE_15_MINUTES = "CACHE_15_MINUTES"
    CACHE_30_MINUTES = "CACHE_30_MINUTES"
    CACHE_1_HOUR = "CACHE_1_HOUR"
    CACHE_6AM_TOMORROW = "CACHE_6AM_TOMORROW"
    CACHE_TWO_WEEKS = "CACHE_TWO_WEEKS"
    RESPECT_SYSTEM_SETTING = "RESPECT_SYSTEM_SETTING"


class CompletenessMethod(StrEnum):
    """org.hisp.dhis.sms.command.CompletenessMethod (DHIS2 v43)."""

    ALL_DATAVALUE = "ALL_DATAVALUE"
    AT_LEAST_ONE_DATAVALUE = "AT_LEAST_ONE_DATAVALUE"
    DO_NOT_MARK_COMPLETE = "DO_NOT_MARK_COMPLETE"


class DashboardItemShape(StrEnum):
    """org.hisp.dhis.dashboard.DashboardItemShape (DHIS2 v43)."""

    NORMAL = "NORMAL"
    DOUBLE_WIDTH = "DOUBLE_WIDTH"
    FULL_WIDTH = "FULL_WIDTH"


class DashboardItemType(StrEnum):
    """org.hisp.dhis.dashboard.DashboardItemType (DHIS2 v43)."""

    VISUALIZATION = "VISUALIZATION"
    EVENT_VISUALIZATION = "EVENT_VISUALIZATION"
    EVENT_CHART = "EVENT_CHART"
    MAP = "MAP"
    EVENT_REPORT = "EVENT_REPORT"
    USERS = "USERS"
    REPORTS = "REPORTS"
    RESOURCES = "RESOURCES"
    TEXT = "TEXT"
    MESSAGES = "MESSAGES"
    APP = "APP"


class DataDimensionType(StrEnum):
    """org.hisp.dhis.common.DataDimensionType (DHIS2 v43)."""

    DISAGGREGATION = "DISAGGREGATION"
    ATTRIBUTE = "ATTRIBUTE"


class DataElementDomain(StrEnum):
    """org.hisp.dhis.dataelement.DataElementDomain (DHIS2 v43)."""

    AGGREGATE = "AGGREGATE"
    TRACKER = "TRACKER"


class DataSetNotificationRecipient(StrEnum):
    """org.hisp.dhis.dataset.notifications.DataSetNotificationRecipient (DHIS2 v43)."""

    ORGANISATION_UNIT_CONTACT = "ORGANISATION_UNIT_CONTACT"
    USER_GROUP = "USER_GROUP"


class DataSetNotificationTrigger(StrEnum):
    """org.hisp.dhis.dataset.notifications.DataSetNotificationTrigger (DHIS2 v43)."""

    DATA_SET_COMPLETION = "DATA_SET_COMPLETION"
    SCHEDULED_DAYS = "SCHEDULED_DAYS"


class DigitGroupSeparator(StrEnum):
    """org.hisp.dhis.common.DigitGroupSeparator (DHIS2 v43)."""

    COMMA = "COMMA"
    SPACE = "SPACE"
    NONE = "NONE"


class DimensionItemType(StrEnum):
    """org.hisp.dhis.common.DimensionItemType (DHIS2 v43)."""

    DATA_ELEMENT = "DATA_ELEMENT"
    DATA_ELEMENT_OPERAND = "DATA_ELEMENT_OPERAND"
    INDICATOR = "INDICATOR"
    REPORTING_RATE = "REPORTING_RATE"
    PROGRAM_DATA_ELEMENT = "PROGRAM_DATA_ELEMENT"
    PROGRAM_DATA_ELEMENT_OPTION = "PROGRAM_DATA_ELEMENT_OPTION"
    PROGRAM_ATTRIBUTE = "PROGRAM_ATTRIBUTE"
    PROGRAM_ATTRIBUTE_OPTION = "PROGRAM_ATTRIBUTE_OPTION"
    PROGRAM_INDICATOR = "PROGRAM_INDICATOR"
    PERIOD = "PERIOD"
    ORGANISATION_UNIT = "ORGANISATION_UNIT"
    CATEGORY_OPTION = "CATEGORY_OPTION"
    OPTION_GROUP = "OPTION_GROUP"
    DATA_ELEMENT_GROUP = "DATA_ELEMENT_GROUP"
    ORGANISATION_UNIT_GROUP = "ORGANISATION_UNIT_GROUP"
    CATEGORY_OPTION_GROUP = "CATEGORY_OPTION_GROUP"
    EXPRESSION_DIMENSION_ITEM = "EXPRESSION_DIMENSION_ITEM"
    SUBEXPRESSION_DIMENSION_ITEM = "SUBEXPRESSION_DIMENSION_ITEM"


class DimensionType(StrEnum):
    """org.hisp.dhis.common.DimensionType (DHIS2 v43)."""

    DATA_X = "DATA_X"
    PROGRAM_DATA_ELEMENT = "PROGRAM_DATA_ELEMENT"
    PROGRAM_ATTRIBUTE = "PROGRAM_ATTRIBUTE"
    PROGRAM_INDICATOR = "PROGRAM_INDICATOR"
    DATA_COLLAPSED = "DATA_COLLAPSED"
    CATEGORY_OPTION_COMBO = "CATEGORY_OPTION_COMBO"
    ATTRIBUTE_OPTION_COMBO = "ATTRIBUTE_OPTION_COMBO"
    PERIOD = "PERIOD"
    ORGANISATION_UNIT = "ORGANISATION_UNIT"
    CATEGORY_OPTION_GROUP_SET = "CATEGORY_OPTION_GROUP_SET"
    DATA_ELEMENT_GROUP_SET = "DATA_ELEMENT_GROUP_SET"
    ORGANISATION_UNIT_GROUP_SET = "ORGANISATION_UNIT_GROUP_SET"
    ORGANISATION_UNIT_GROUP = "ORGANISATION_UNIT_GROUP"
    CATEGORY = "CATEGORY"
    OPTION_GROUP_SET = "OPTION_GROUP_SET"
    VALIDATION_RULE = "VALIDATION_RULE"
    STATIC = "STATIC"
    ORGANISATION_UNIT_LEVEL = "ORGANISATION_UNIT_LEVEL"
    PROGRAM_STATUS = "PROGRAM_STATUS"


class DisplayDensity(StrEnum):
    """org.hisp.dhis.common.DisplayDensity (DHIS2 v43)."""

    COMFORTABLE = "COMFORTABLE"
    NORMAL = "NORMAL"
    COMPACT = "COMPACT"
    NONE = "NONE"


class EnrollmentStatus(StrEnum):
    """org.hisp.dhis.program.EnrollmentStatus (DHIS2 v43)."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class EventDataType(StrEnum):
    """org.hisp.dhis.analytics.EventDataType (DHIS2 v43)."""

    AGGREGATED_VALUES = "AGGREGATED_VALUES"
    EVENTS = "EVENTS"


class EventOutputType(StrEnum):
    """org.hisp.dhis.analytics.EventOutputType (DHIS2 v43)."""

    EVENT = "EVENT"
    ENROLLMENT = "ENROLLMENT"
    TRACKED_ENTITY_INSTANCE = "TRACKED_ENTITY_INSTANCE"


class EventStatus(StrEnum):
    """org.hisp.dhis.event.EventStatus (DHIS2 v43)."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    VISITED = "VISITED"
    SCHEDULE = "SCHEDULE"
    OVERDUE = "OVERDUE"
    SKIPPED = "SKIPPED"


class EventVisualizationType(StrEnum):
    """org.hisp.dhis.eventvisualization.EventVisualizationType (DHIS2 v43)."""

    COLUMN = "COLUMN"
    STACKED_COLUMN = "STACKED_COLUMN"
    BAR = "BAR"
    STACKED_BAR = "STACKED_BAR"
    LINE = "LINE"
    LINE_LIST = "LINE_LIST"
    AREA = "AREA"
    STACKED_AREA = "STACKED_AREA"
    PIE = "PIE"
    RADAR = "RADAR"
    GAUGE = "GAUGE"
    YEAR_OVER_YEAR_LINE = "YEAR_OVER_YEAR_LINE"
    YEAR_OVER_YEAR_COLUMN = "YEAR_OVER_YEAR_COLUMN"
    SINGLE_VALUE = "SINGLE_VALUE"
    PIVOT_TABLE = "PIVOT_TABLE"
    SCATTER = "SCATTER"
    BUBBLE = "BUBBLE"


class FeatureType(StrEnum):
    """org.hisp.dhis.organisationunit.FeatureType (DHIS2 v43)."""

    NONE = "NONE"
    MULTI_POLYGON = "MULTI_POLYGON"
    POLYGON = "POLYGON"
    POINT = "POINT"
    SYMBOL = "SYMBOL"


class FileResourceDomain(StrEnum):
    """org.hisp.dhis.fileresource.FileResourceDomain (DHIS2 v43)."""

    DATA_VALUE = "DATA_VALUE"
    DOCUMENT = "DOCUMENT"
    MESSAGE_ATTACHMENT = "MESSAGE_ATTACHMENT"
    USER_AVATAR = "USER_AVATAR"
    ORG_UNIT = "ORG_UNIT"
    ICON = "ICON"
    JOB_DATA = "JOB_DATA"


class FileResourceStorageStatus(StrEnum):
    """org.hisp.dhis.fileresource.FileResourceStorageStatus (DHIS2 v43)."""

    NONE = "NONE"
    PENDING = "PENDING"
    STORED = "STORED"


class FontSize(StrEnum):
    """org.hisp.dhis.common.FontSize (DHIS2 v43)."""

    LARGE = "LARGE"
    NORMAL = "NORMAL"
    SMALL = "SMALL"


class FormType(StrEnum):
    """org.hisp.dhis.dataset.FormType (DHIS2 v43)."""

    DEFAULT = "DEFAULT"
    CUSTOM = "CUSTOM"
    SECTION = "SECTION"
    SECTION_MULTIORG = "SECTION_MULTIORG"


class HideEmptyItemStrategy(StrEnum):
    """org.hisp.dhis.common.HideEmptyItemStrategy (DHIS2 v43)."""

    NONE = "NONE"
    BEFORE_FIRST = "BEFORE_FIRST"
    AFTER_LAST = "AFTER_LAST"
    BEFORE_FIRST_AFTER_LAST = "BEFORE_FIRST_AFTER_LAST"
    ALL = "ALL"


class ImageFormat(StrEnum):
    """org.hisp.dhis.mapping.ImageFormat (DHIS2 v43)."""

    PNG = "PNG"
    JPG = "JPG"


class Importance(StrEnum):
    """org.hisp.dhis.validation.Importance (DHIS2 v43)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class JobStatus(StrEnum):
    """org.hisp.dhis.scheduling.JobStatus (DHIS2 v43)."""

    RUNNING = "RUNNING"
    SCHEDULED = "SCHEDULED"
    DISABLED = "DISABLED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    NOT_STARTED = "NOT_STARTED"


class JobType(StrEnum):
    """org.hisp.dhis.scheduling.JobType (DHIS2 v43)."""

    DATA_INTEGRITY = "DATA_INTEGRITY"
    DATA_INTEGRITY_DETAILS = "DATA_INTEGRITY_DETAILS"
    RESOURCE_TABLE = "RESOURCE_TABLE"
    ANALYTICS_TABLE = "ANALYTICS_TABLE"
    CONTINUOUS_ANALYTICS_TABLE = "CONTINUOUS_ANALYTICS_TABLE"
    SINGLE_EVENT_DATA_SYNC = "SINGLE_EVENT_DATA_SYNC"
    TRACKED_ENTITY_DATA_SYNC = "TRACKED_ENTITY_DATA_SYNC"
    DATA_SYNC = "DATA_SYNC"
    META_DATA_SYNC = "META_DATA_SYNC"
    AGGREGATE_DATA_EXCHANGE = "AGGREGATE_DATA_EXCHANGE"
    SEND_SCHEDULED_MESSAGE = "SEND_SCHEDULED_MESSAGE"
    PROGRAM_NOTIFICATIONS = "PROGRAM_NOTIFICATIONS"
    MONITORING = "MONITORING"
    HTML_PUSH_ANALYTICS = "HTML_PUSH_ANALYTICS"
    TRACKER_TRIGRAM_INDEX_MAINTENANCE = "TRACKER_TRIGRAM_INDEX_MAINTENANCE"
    PREDICTOR = "PREDICTOR"
    MATERIALIZED_SQL_VIEW_UPDATE = "MATERIALIZED_SQL_VIEW_UPDATE"
    DISABLE_INACTIVE_USERS = "DISABLE_INACTIVE_USERS"
    TEST = "TEST"
    LOCK_EXCEPTION_CLEANUP = "LOCK_EXCEPTION_CLEANUP"
    MOCK = "MOCK"
    SMS_SEND = "SMS_SEND"
    SMS_INBOUND_PROCESSING = "SMS_INBOUND_PROCESSING"
    TRACKER_IMPORT_JOB = "TRACKER_IMPORT_JOB"
    TRACKER_IMPORT_NOTIFICATION_JOB = "TRACKER_IMPORT_NOTIFICATION_JOB"
    TRACKER_IMPORT_RULE_ENGINE_JOB = "TRACKER_IMPORT_RULE_ENGINE_JOB"
    IMAGE_PROCESSING = "IMAGE_PROCESSING"
    COMPLETE_DATA_SET_REGISTRATION_IMPORT = "COMPLETE_DATA_SET_REGISTRATION_IMPORT"
    DATAVALUE_IMPORT_INTERNAL = "DATAVALUE_IMPORT_INTERNAL"
    METADATA_IMPORT = "METADATA_IMPORT"
    DATAVALUE_IMPORT = "DATAVALUE_IMPORT"
    GEOJSON_IMPORT = "GEOJSON_IMPORT"
    GML_IMPORT = "GML_IMPORT"
    HOUSEKEEPING = "HOUSEKEEPING"
    DATA_VALUE_TRIM = "DATA_VALUE_TRIM"
    DATA_SET_NOTIFICATION = "DATA_SET_NOTIFICATION"
    CREDENTIALS_EXPIRY_ALERT = "CREDENTIALS_EXPIRY_ALERT"
    DATA_STATISTICS = "DATA_STATISTICS"
    FILE_RESOURCE_CLEANUP = "FILE_RESOURCE_CLEANUP"
    ACCOUNT_EXPIRY_ALERT = "ACCOUNT_EXPIRY_ALERT"
    VALIDATION_RESULTS_NOTIFICATION = "VALIDATION_RESULTS_NOTIFICATION"
    REMOVE_USED_OR_EXPIRED_RESERVED_VALUES = "REMOVE_USED_OR_EXPIRED_RESERVED_VALUES"
    SYSTEM_VERSION_UPDATE_CHECK = "SYSTEM_VERSION_UPDATE_CHECK"


class LegendDisplayStrategy(StrEnum):
    """org.hisp.dhis.legend.LegendDisplayStrategy (DHIS2 v43)."""

    FIXED = "FIXED"
    BY_DATA_ITEM = "BY_DATA_ITEM"


class LegendDisplayStyle(StrEnum):
    """org.hisp.dhis.legend.LegendDisplayStyle (DHIS2 v43)."""

    FILL = "FILL"
    TEXT = "TEXT"


class MapLayerPosition(StrEnum):
    """org.hisp.dhis.mapping.MapLayerPosition (DHIS2 v43)."""

    BASEMAP = "BASEMAP"
    OVERLAY = "OVERLAY"


class MapService(StrEnum):
    """org.hisp.dhis.mapping.MapService (DHIS2 v43)."""

    WMS = "WMS"
    TMS = "TMS"
    XYZ = "XYZ"
    VECTOR_STYLE = "VECTOR_STYLE"
    GEOJSON_URL = "GEOJSON_URL"
    ARCGIS_FEATURE = "ARCGIS_FEATURE"


class MapViewRenderingStrategy(StrEnum):
    """org.hisp.dhis.mapping.MapViewRenderingStrategy (DHIS2 v43)."""

    SINGLE = "SINGLE"
    SPLIT_BY_PERIOD = "SPLIT_BY_PERIOD"
    TIMELINE = "TIMELINE"


class MappingEventStatus(StrEnum):
    """org.hisp.dhis.mapping.EventStatus (DHIS2 v43)."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    SCHEDULE = "SCHEDULE"
    OVERDUE = "OVERDUE"
    SKIPPED = "SKIPPED"


class MessageConversationPriority(StrEnum):
    """org.hisp.dhis.message.MessageConversationPriority (DHIS2 v43)."""

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MessageConversationStatus(StrEnum):
    """org.hisp.dhis.message.MessageConversationStatus (DHIS2 v43)."""

    NONE = "NONE"
    OPEN = "OPEN"
    PENDING = "PENDING"
    INVALID = "INVALID"
    SOLVED = "SOLVED"


class MessageType(StrEnum):
    """org.hisp.dhis.message.MessageType (DHIS2 v43)."""

    PRIVATE = "PRIVATE"
    SYSTEM = "SYSTEM"
    VALIDATION_RESULT = "VALIDATION_RESULT"
    TICKET = "TICKET"
    SYSTEM_VERSION_UPDATE = "SYSTEM_VERSION_UPDATE"


class MetadataProposalStatus(StrEnum):
    """org.hisp.dhis.metadata.MetadataProposalStatus (DHIS2 v43)."""

    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_UPDATE = "NEEDS_UPDATE"


class MetadataProposalTarget(StrEnum):
    """org.hisp.dhis.metadata.MetadataProposalTarget (DHIS2 v43)."""

    ORGANISATION_UNIT = "ORGANISATION_UNIT"


class MetadataProposalType(StrEnum):
    """org.hisp.dhis.metadata.MetadataProposalType (DHIS2 v43)."""

    ADD = "ADD"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"


class MissingValueStrategy(StrEnum):
    """org.hisp.dhis.expression.MissingValueStrategy (DHIS2 v43)."""

    SKIP_IF_ANY_VALUE_MISSING = "SKIP_IF_ANY_VALUE_MISSING"
    SKIP_IF_ALL_VALUES_MISSING = "SKIP_IF_ALL_VALUES_MISSING"
    NEVER_SKIP = "NEVER_SKIP"


class NormalizedOutlierMethod(StrEnum):
    """org.hisp.dhis.visualization.NormalizedOutlierMethod (DHIS2 v43)."""

    Y_RESIDUALS_LINEAR = "Y_RESIDUALS_LINEAR"


class NotificationTrigger(StrEnum):
    """org.hisp.dhis.program.notification.NotificationTrigger (DHIS2 v43)."""

    ENROLLMENT = "ENROLLMENT"
    COMPLETION = "COMPLETION"
    PROGRAM_RULE = "PROGRAM_RULE"
    SCHEDULED_DAYS_DUE_DATE = "SCHEDULED_DAYS_DUE_DATE"
    SCHEDULED_DAYS_INCIDENT_DATE = "SCHEDULED_DAYS_INCIDENT_DATE"
    SCHEDULED_DAYS_ENROLLMENT_DATE = "SCHEDULED_DAYS_ENROLLMENT_DATE"


class NumberType(StrEnum):
    """org.hisp.dhis.analytics.NumberType (DHIS2 v43)."""

    VALUE = "VALUE"
    ROW_PERCENTAGE = "ROW_PERCENTAGE"
    COLUMN_PERCENTAGE = "COLUMN_PERCENTAGE"


class Operator(StrEnum):
    """org.hisp.dhis.expression.Operator (DHIS2 v43)."""

    EQUAL_TO = "equal_to"
    NOT_EQUAL_TO = "not_equal_to"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL_TO = "greater_than_or_equal_to"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL_TO = "less_than_or_equal_to"
    COMPULSORY_PAIR = "compulsory_pair"
    EXCLUSIVE_PAIR = "exclusive_pair"


class OrganisationUnitDescendants(StrEnum):
    """org.hisp.dhis.common.OrganisationUnitDescendants (DHIS2 v43)."""

    SELECTED = "SELECTED"
    DESCENDANTS = "DESCENDANTS"


class OrganisationUnitSelectionMode(StrEnum):
    """org.hisp.dhis.common.OrganisationUnitSelectionMode (DHIS2 v43)."""

    SELECTED = "SELECTED"
    CHILDREN = "CHILDREN"
    DESCENDANTS = "DESCENDANTS"
    ACCESSIBLE = "ACCESSIBLE"
    CAPTURE = "CAPTURE"
    ALL = "ALL"


class OutlierMethod(StrEnum):
    """org.hisp.dhis.visualization.OutlierMethod (DHIS2 v43)."""

    IQR = "IQR"
    STANDARD_Z_SCORE = "STANDARD_Z_SCORE"
    MODIFIED_Z_SCORE = "MODIFIED_Z_SCORE"


class ParserType(StrEnum):
    """org.hisp.dhis.sms.parse.ParserType (DHIS2 v43)."""

    KEY_VALUE_PARSER = "KEY_VALUE_PARSER"
    ALERT_PARSER = "ALERT_PARSER"
    UNREGISTERED_PARSER = "UNREGISTERED_PARSER"
    TRACKED_ENTITY_REGISTRATION_PARSER = "TRACKED_ENTITY_REGISTRATION_PARSER"
    PROGRAM_STAGE_DATAENTRY_PARSER = "PROGRAM_STAGE_DATAENTRY_PARSER"
    EVENT_REGISTRATION_PARSER = "EVENT_REGISTRATION_PARSER"


class Position(StrEnum):
    """org.hisp.dhis.dashboard.design.Position (DHIS2 v43)."""

    START = "START"
    END = "END"


class ProgramNotificationRecipient(StrEnum):
    """org.hisp.dhis.program.notification.ProgramNotificationRecipient (DHIS2 v43)."""

    TRACKED_ENTITY_INSTANCE = "TRACKED_ENTITY_INSTANCE"
    ORGANISATION_UNIT_CONTACT = "ORGANISATION_UNIT_CONTACT"
    USERS_AT_ORGANISATION_UNIT = "USERS_AT_ORGANISATION_UNIT"
    USER_GROUP = "USER_GROUP"
    PROGRAM_ATTRIBUTE = "PROGRAM_ATTRIBUTE"
    DATA_ELEMENT = "DATA_ELEMENT"
    WEB_HOOK = "WEB_HOOK"


class ProgramRuleActionEvaluationTime(StrEnum):
    """org.hisp.dhis.programrule.ProgramRuleActionEvaluationTime (DHIS2 v43)."""

    ON_DATA_ENTRY = "ON_DATA_ENTRY"
    ON_COMPLETE = "ON_COMPLETE"
    ALWAYS = "ALWAYS"


class ProgramRuleActionType(StrEnum):
    """org.hisp.dhis.programrule.ProgramRuleActionType (DHIS2 v43)."""

    DISPLAYTEXT = "DISPLAYTEXT"
    DISPLAYKEYVALUEPAIR = "DISPLAYKEYVALUEPAIR"
    HIDEFIELD = "HIDEFIELD"
    HIDESECTION = "HIDESECTION"
    HIDEPROGRAMSTAGE = "HIDEPROGRAMSTAGE"
    ASSIGN = "ASSIGN"
    SHOWWARNING = "SHOWWARNING"
    WARNINGONCOMPLETE = "WARNINGONCOMPLETE"
    SHOWERROR = "SHOWERROR"
    ERRORONCOMPLETE = "ERRORONCOMPLETE"
    SCHEDULEEVENT = "SCHEDULEEVENT"
    CREATEEVENT = "CREATEEVENT"
    SETMANDATORYFIELD = "SETMANDATORYFIELD"
    SENDMESSAGE = "SENDMESSAGE"
    SCHEDULEMESSAGE = "SCHEDULEMESSAGE"
    HIDEOPTION = "HIDEOPTION"
    SHOWOPTIONGROUP = "SHOWOPTIONGROUP"
    HIDEOPTIONGROUP = "HIDEOPTIONGROUP"


class ProgramRuleVariableSourceType(StrEnum):
    """org.hisp.dhis.programrule.ProgramRuleVariableSourceType (DHIS2 v43)."""

    DATAELEMENT_NEWEST_EVENT_PROGRAM_STAGE = "DATAELEMENT_NEWEST_EVENT_PROGRAM_STAGE"
    DATAELEMENT_NEWEST_EVENT_PROGRAM = "DATAELEMENT_NEWEST_EVENT_PROGRAM"
    DATAELEMENT_CURRENT_EVENT = "DATAELEMENT_CURRENT_EVENT"
    DATAELEMENT_PREVIOUS_EVENT = "DATAELEMENT_PREVIOUS_EVENT"
    CALCULATED_VALUE = "CALCULATED_VALUE"
    TEI_ATTRIBUTE = "TEI_ATTRIBUTE"


class ProgramType(StrEnum):
    """org.hisp.dhis.program.ProgramType (DHIS2 v43)."""

    WITH_REGISTRATION = "WITH_REGISTRATION"
    WITHOUT_REGISTRATION = "WITHOUT_REGISTRATION"


class QueryOperator(StrEnum):
    """org.hisp.dhis.common.QueryOperator (DHIS2 v43)."""

    EQ = "EQ"
    GT = "GT"
    GE = "GE"
    LT = "LT"
    LE = "LE"
    LIKE = "LIKE"
    IN_ = "IN"
    SW = "SW"
    EW = "EW"
    NULL = "NULL"
    NNULL = "NNULL"
    IEQ = "IEQ"
    NE = "NE"
    NEQ = "NEQ"
    NIEQ = "NIEQ"
    NLIKE = "NLIKE"
    ILIKE = "ILIKE"
    NILIKE = "NILIKE"


class RegressionType(StrEnum):
    """org.hisp.dhis.common.RegressionType (DHIS2 v43)."""

    NONE = "NONE"
    LINEAR = "LINEAR"
    POLYNOMIAL = "POLYNOMIAL"
    LOESS = "LOESS"


class RelationshipEntity(StrEnum):
    """org.hisp.dhis.relationship.RelationshipEntity (DHIS2 v43)."""

    TRACKED_ENTITY_INSTANCE = "TRACKED_ENTITY_INSTANCE"
    PROGRAM_INSTANCE = "PROGRAM_INSTANCE"
    PROGRAM_STAGE_INSTANCE = "PROGRAM_STAGE_INSTANCE"


class ReportType(StrEnum):
    """org.hisp.dhis.report.ReportType (DHIS2 v43)."""

    JASPER_REPORT_TABLE = "JASPER_REPORT_TABLE"
    JASPER_JDBC = "JASPER_JDBC"
    HTML = "HTML"


class ReportingRateMetric(StrEnum):
    """org.hisp.dhis.common.ReportingRateMetric (DHIS2 v43)."""

    REPORTING_RATE = "REPORTING_RATE"
    REPORTING_RATE_ON_TIME = "REPORTING_RATE_ON_TIME"
    ACTUAL_REPORTS = "ACTUAL_REPORTS"
    ACTUAL_REPORTS_ON_TIME = "ACTUAL_REPORTS_ON_TIME"
    EXPECTED_REPORTS = "EXPECTED_REPORTS"


class ResourceTableType(StrEnum):
    """org.hisp.dhis.resourcetable.ResourceTableType (DHIS2 v43)."""

    ORG_UNIT_STRUCTURE = "ORG_UNIT_STRUCTURE"
    DATA_SET_ORG_UNIT_CATEGORY = "DATA_SET_ORG_UNIT_CATEGORY"
    CATEGORY_OPTION_COMBO_NAME = "CATEGORY_OPTION_COMBO_NAME"
    DATA_ELEMENT_GROUP_SET_STRUCTURE = "DATA_ELEMENT_GROUP_SET_STRUCTURE"
    INDICATOR_GROUP_SET_STRUCTURE = "INDICATOR_GROUP_SET_STRUCTURE"
    ORG_UNIT_GROUP_SET_STRUCTURE = "ORG_UNIT_GROUP_SET_STRUCTURE"
    CATEGORY_STRUCTURE = "CATEGORY_STRUCTURE"
    DATA_ELEMENT_STRUCTURE = "DATA_ELEMENT_STRUCTURE"
    DATA_SET = "DATA_SET"
    PERIOD_STRUCTURE = "PERIOD_STRUCTURE"
    DATE_PERIOD_STRUCTURE = "DATE_PERIOD_STRUCTURE"
    DATA_ELEMENT_CATEGORY_OPTION_COMBO = "DATA_ELEMENT_CATEGORY_OPTION_COMBO"
    DATA_APPROVAL_REMAP_LEVEL = "DATA_APPROVAL_REMAP_LEVEL"
    DATA_APPROVAL_MIN_LEVEL = "DATA_APPROVAL_MIN_LEVEL"
    TEI_RELATIONSHIP_COUNT = "TEI_RELATIONSHIP_COUNT"


class SchedulingType(StrEnum):
    """org.hisp.dhis.scheduling.SchedulingType (DHIS2 v43)."""

    CRON = "CRON"
    FIXED_DELAY = "FIXED_DELAY"
    ONCE_ASAP = "ONCE_ASAP"


class SendStrategy(StrEnum):
    """org.hisp.dhis.notification.SendStrategy (DHIS2 v43)."""

    COLLECTIVE_SUMMARY = "COLLECTIVE_SUMMARY"
    SINGLE_NOTIFICATION = "SINGLE_NOTIFICATION"


class SqlViewType(StrEnum):
    """org.hisp.dhis.sqlview.SqlViewType (DHIS2 v43)."""

    VIEW = "VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED_VIEW"
    QUERY = "QUERY"


class ThematicMapType(StrEnum):
    """org.hisp.dhis.mapping.ThematicMapType (DHIS2 v43)."""

    CHOROPLETH = "CHOROPLETH"
    BUBBLE = "BUBBLE"


class TotalAggregationType(StrEnum):
    """org.hisp.dhis.common.TotalAggregationType (DHIS2 v43)."""

    NONE = "NONE"
    SUM = "SUM"
    AVERAGE = "AVERAGE"


class UserOrgUnitType(StrEnum):
    """org.hisp.dhis.common.UserOrgUnitType (DHIS2 v43)."""

    DATA_CAPTURE = "DATA_CAPTURE"
    DATA_OUTPUT = "DATA_OUTPUT"
    TEI_SEARCH = "TEI_SEARCH"


class ValidationStrategy(StrEnum):
    """org.hisp.dhis.program.ValidationStrategy (DHIS2 v43)."""

    ON_COMPLETE = "ON_COMPLETE"
    ON_UPDATE_AND_INSERT = "ON_UPDATE_AND_INSERT"


class ValueType(StrEnum):
    """org.hisp.dhis.common.ValueType (DHIS2 v43)."""

    TEXT = "TEXT"
    LONG_TEXT = "LONG_TEXT"
    MULTI_TEXT = "MULTI_TEXT"
    LETTER = "LETTER"
    PHONE_NUMBER = "PHONE_NUMBER"
    EMAIL = "EMAIL"
    BOOLEAN = "BOOLEAN"
    TRUE_ONLY = "TRUE_ONLY"
    DATE = "DATE"
    DATETIME = "DATETIME"
    TIME = "TIME"
    NUMBER = "NUMBER"
    UNIT_INTERVAL = "UNIT_INTERVAL"
    PERCENTAGE = "PERCENTAGE"
    INTEGER = "INTEGER"
    INTEGER_POSITIVE = "INTEGER_POSITIVE"
    INTEGER_NEGATIVE = "INTEGER_NEGATIVE"
    INTEGER_ZERO_OR_POSITIVE = "INTEGER_ZERO_OR_POSITIVE"
    USERNAME = "USERNAME"
    COORDINATE = "COORDINATE"
    ORGANISATION_UNIT = "ORGANISATION_UNIT"
    REFERENCE = "REFERENCE"
    AGE = "AGE"
    URL = "URL"
    FILE_RESOURCE = "FILE_RESOURCE"
    IMAGE = "IMAGE"
    GEOJSON = "GEOJSON"


class VersionType(StrEnum):
    """org.hisp.dhis.metadata.version.VersionType (DHIS2 v43)."""

    BEST_EFFORT = "BEST_EFFORT"
    ATOMIC = "ATOMIC"


class VisualizationType(StrEnum):
    """org.hisp.dhis.visualization.VisualizationType (DHIS2 v43)."""

    COLUMN = "COLUMN"
    STACKED_COLUMN = "STACKED_COLUMN"
    BAR = "BAR"
    STACKED_BAR = "STACKED_BAR"
    LINE = "LINE"
    AREA = "AREA"
    STACKED_AREA = "STACKED_AREA"
    PIE = "PIE"
    RADAR = "RADAR"
    GAUGE = "GAUGE"
    YEAR_OVER_YEAR_LINE = "YEAR_OVER_YEAR_LINE"
    YEAR_OVER_YEAR_COLUMN = "YEAR_OVER_YEAR_COLUMN"
    SCATTER = "SCATTER"
    BUBBLE = "BUBBLE"
    SINGLE_VALUE = "SINGLE_VALUE"
    PIVOT_TABLE = "PIVOT_TABLE"
    OUTLIER_TABLE = "OUTLIER_TABLE"
