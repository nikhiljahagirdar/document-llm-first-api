from enum import Enum

class TenantTypeSchema(str, Enum):
    INDIVIDUAL = "individual"
    ENTERPRISE = "enterprise"
