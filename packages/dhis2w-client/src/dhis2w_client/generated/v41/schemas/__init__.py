"""Generated DHIS2 v41 pydantic schemas."""

from __future__ import annotations

from .access import Access
from .aggregate_data_exchange import AggregateDataExchange
from .analytics_period_boundary import AnalyticsPeriodBoundary
from .analytics_table_hook import AnalyticsTableHook
from .api_token import ApiToken
from .attribute import Attribute
from .attribute_value import AttributeValue
from .axis import Axis
from .category import Category
from .category_combo import CategoryCombo
from .category_dimension import CategoryDimension
from .category_option import CategoryOption
from .category_option_combo import CategoryOptionCombo
from .category_option_group import CategoryOptionGroup
from .category_option_group_set import CategoryOptionGroupSet
from .category_option_group_set_dimension import CategoryOptionGroupSetDimension
from .constant import Constant
from .dashboard import Dashboard
from .dashboard_item import DashboardItem
from .data_approval_level import DataApprovalLevel
from .data_approval_workflow import DataApprovalWorkflow
from .data_element import DataElement
from .data_element_group import DataElementGroup
from .data_element_group_set import DataElementGroupSet
from .data_element_group_set_dimension import DataElementGroupSetDimension
from .data_element_operand import DataElementOperand
from .data_entry_form import DataEntryForm
from .data_input_period import DataInputPeriod
from .data_set import DataSet
from .data_set_element import DataSetElement
from .data_set_notification_template import DataSetNotificationTemplate
from .datastore_entry import DatastoreEntry
from .document import Document
from .enrollment import Enrollment
from .event import Event
from .event_chart import EventChart
from .event_filter import EventFilter
from .event_hook import EventHook
from .event_repetition import EventRepetition
from .event_report import EventReport
from .event_visualization import EventVisualization
from .expression import Expression
from .expression_dimension_item import ExpressionDimensionItem
from .external_map_layer import ExternalMapLayer
from .file_resource import FileResource
from .icon import Icon
from .indicator import Indicator
from .indicator_group import IndicatorGroup
from .indicator_group_set import IndicatorGroupSet
from .indicator_type import IndicatorType
from .interpretation import Interpretation
from .interpretation_comment import InterpretationComment
from .item_config import ItemConfig
from .job_configuration import JobConfiguration
from .legend import Legend
from .legend_definitions import LegendDefinitions
from .legend_set import LegendSet
from .map import Map
from .message_conversation import MessageConversation
from .metadata_proposal import MetadataProposal
from .metadata_version import MetadataVersion
from .min_max_data_element import MinMaxDataElement
from .o_auth2_client import OAuth2Client
from .object_style import ObjectStyle
from .option import Option
from .option_group import OptionGroup
from .option_group_set import OptionGroupSet
from .option_set import OptionSet
from .organisation_unit import OrganisationUnit
from .organisation_unit_group import OrganisationUnitGroup
from .organisation_unit_group_set import OrganisationUnitGroupSet
from .organisation_unit_group_set_dimension import OrganisationUnitGroupSetDimension
from .organisation_unit_level import OrganisationUnitLevel
from .outlier_analysis import OutlierAnalysis
from .predictor import Predictor
from .predictor_group import PredictorGroup
from .program import Program
from .program_data_element_dimension_item import ProgramDataElementDimensionItem
from .program_indicator import ProgramIndicator
from .program_indicator_group import ProgramIndicatorGroup
from .program_notification_template import ProgramNotificationTemplate
from .program_rule import ProgramRule
from .program_rule_action import ProgramRuleAction
from .program_rule_variable import ProgramRuleVariable
from .program_section import ProgramSection
from .program_stage import ProgramStage
from .program_stage_data_element import ProgramStageDataElement
from .program_stage_section import ProgramStageSection
from .program_stage_working_list import ProgramStageWorkingList
from .program_tracked_entity_attribute import ProgramTrackedEntityAttribute
from .program_tracked_entity_attribute_dimension_item import ProgramTrackedEntityAttributeDimensionItem
from .push_analysis import PushAnalysis
from .relationship import Relationship
from .relationship_constraint import RelationshipConstraint
from .relationship_item import RelationshipItem
from .relationship_type import RelationshipType
from .report import Report
from .reporting_rate import ReportingRate
from .route import Route
from .s_m_s_command import SMSCommand
from .section import Section
from .series_key import SeriesKey
from .sharing import Sharing
from .sql_view import SqlView
from .tracked_entity import TrackedEntity
from .tracked_entity_attribute import TrackedEntityAttribute
from .tracked_entity_attribute_value import TrackedEntityAttributeValue
from .tracked_entity_data_element_dimension import TrackedEntityDataElementDimension
from .tracked_entity_filter import TrackedEntityFilter
from .tracked_entity_program_indicator_dimension import TrackedEntityProgramIndicatorDimension
from .tracked_entity_type import TrackedEntityType
from .tracked_entity_type_attribute import TrackedEntityTypeAttribute
from .user import User
from .user_access import UserAccess
from .user_credentials_dto import UserCredentialsDto
from .user_group import UserGroup
from .user_group_access import UserGroupAccess
from .user_role import UserRole
from .validation_notification_template import ValidationNotificationTemplate
from .validation_result import ValidationResult
from .validation_rule import ValidationRule
from .validation_rule_group import ValidationRuleGroup
from .visualization import Visualization

__all__ = [
    "Access",
    "AggregateDataExchange",
    "AnalyticsPeriodBoundary",
    "AnalyticsTableHook",
    "ApiToken",
    "Attribute",
    "AttributeValue",
    "Axis",
    "Category",
    "CategoryCombo",
    "CategoryDimension",
    "CategoryOption",
    "CategoryOptionCombo",
    "CategoryOptionGroup",
    "CategoryOptionGroupSet",
    "CategoryOptionGroupSetDimension",
    "Constant",
    "Dashboard",
    "DashboardItem",
    "DataApprovalLevel",
    "DataApprovalWorkflow",
    "DataElement",
    "DataElementGroup",
    "DataElementGroupSet",
    "DataElementGroupSetDimension",
    "DataElementOperand",
    "DataEntryForm",
    "DataInputPeriod",
    "DataSet",
    "DataSetElement",
    "DataSetNotificationTemplate",
    "DatastoreEntry",
    "Document",
    "Enrollment",
    "Event",
    "EventChart",
    "EventFilter",
    "EventHook",
    "EventRepetition",
    "EventReport",
    "EventVisualization",
    "Expression",
    "ExpressionDimensionItem",
    "ExternalMapLayer",
    "FileResource",
    "Icon",
    "Indicator",
    "IndicatorGroup",
    "IndicatorGroupSet",
    "IndicatorType",
    "Interpretation",
    "InterpretationComment",
    "ItemConfig",
    "JobConfiguration",
    "Legend",
    "LegendDefinitions",
    "LegendSet",
    "Map",
    "MessageConversation",
    "MetadataProposal",
    "MetadataVersion",
    "MinMaxDataElement",
    "OAuth2Client",
    "ObjectStyle",
    "Option",
    "OptionGroup",
    "OptionGroupSet",
    "OptionSet",
    "OrganisationUnit",
    "OrganisationUnitGroup",
    "OrganisationUnitGroupSet",
    "OrganisationUnitGroupSetDimension",
    "OrganisationUnitLevel",
    "OutlierAnalysis",
    "Predictor",
    "PredictorGroup",
    "Program",
    "ProgramDataElementDimensionItem",
    "ProgramIndicator",
    "ProgramIndicatorGroup",
    "ProgramNotificationTemplate",
    "ProgramRule",
    "ProgramRuleAction",
    "ProgramRuleVariable",
    "ProgramSection",
    "ProgramStage",
    "ProgramStageDataElement",
    "ProgramStageSection",
    "ProgramStageWorkingList",
    "ProgramTrackedEntityAttribute",
    "ProgramTrackedEntityAttributeDimensionItem",
    "PushAnalysis",
    "Relationship",
    "RelationshipConstraint",
    "RelationshipItem",
    "RelationshipType",
    "Report",
    "ReportingRate",
    "Route",
    "SMSCommand",
    "Section",
    "SeriesKey",
    "Sharing",
    "SqlView",
    "TrackedEntity",
    "TrackedEntityAttribute",
    "TrackedEntityAttributeValue",
    "TrackedEntityDataElementDimension",
    "TrackedEntityFilter",
    "TrackedEntityProgramIndicatorDimension",
    "TrackedEntityType",
    "TrackedEntityTypeAttribute",
    "User",
    "UserAccess",
    "UserCredentialsDto",
    "UserGroup",
    "UserGroupAccess",
    "UserRole",
    "ValidationNotificationTemplate",
    "ValidationResult",
    "ValidationRule",
    "ValidationRuleGroup",
    "Visualization",
]
