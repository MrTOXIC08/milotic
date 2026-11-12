"""Global constants for the Milotic MCP server."""

NAME = "Milotic"
VERSION = "0.1.0"

# --- Service/Category Names ---
CATEGORY_SYSTEM = "system"
CATEGORY_MARKET = "market"
CATEGORY_ACCOUNT = "account"
CATEGORY_TRADING = "trading"
CATEGORY_RESEARCH = "research"
CATEGORY_ALERTS = "alerts"

# --- Request Identification ---
HEADER_REQUEST_ID = "X-Req-ID"

# --- Authentication Headers ---
HEADER_AUTHORIZATION = "Authorization"
HEADER_AUTH_TOKEN = "X-AuthToken"
HEADER_ASL_TOKEN = "X-AslToken"
HEADER_REFRESH_TOKEN = "X-Refresh-Token"

# --- Device & App Identity ---
HEADER_DEVICE_ID = "X-DeviceId"
HEADER_APP_ID = "X-AppId"

# --- Crypto / Encryption ---
HEADER_API_CLIENT_ID = "X-API-Client-Id"
HEADER_API_ENCRYPTION_KEY = "X-API-Encryption-Key"

# --- Account ---
HEADER_SUB_ACCOUNT_ID = "X-SubAccountID"

# --- Messaging ---
HEADER_MSG_SEQUENCE = "X-MsgSequence"
HEADER_MSG_GROUP = "X-MsgGroup"

# --- Source & Channel ---
HEADER_SOURCE = "X-Source"
HEADER_SOURCE_CHANNEL = "X-SourceChannel"

# --- Security & Segmentation ---
HEADER_SECURITY_INFO_PROJECTION = "X-SecurityInfoProjection"
SECURITY_INFO_PROJECTION_SCRIPT_ID = "scriptId"
SECURITY_INFO_PROJECTION_SCRIPT_ID_SEGMENT = "scriptId,segment"
SECURITY_INFO_PROJECTION_POSITIONS = (
    "scriptId,coCode,exchange,segment,odinCode,instrument,aslAllowed,"
    "closePrice,isinCode,assetClass,securityDescription,symbol"
)

# --- Cache & TTL Settings ---
DEFAULT_CACHE_TTL_SECONDS = 3600

# --- Resilience Defaults ---
DEFAULT_MAX_CONCURRENT_REQUESTS = 20
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 5
