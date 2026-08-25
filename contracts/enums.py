"""共享枚举：意图类型、场景、风险/规则等级、知识状态。"""
from enum import Enum


class IntentType(str, Enum):
    # 核心外设
    GPIO = "GPIO"
    TIM = "TIM"
    UART = "UART"
    SPI = "SPI"
    I2C = "I2C"
    ADC = "ADC"
    DMA = "DMA"
    # 扩展外设
    CAN = "CAN"
    CRC = "CRC"
    CRYP = "CRYP"
    DAC = "DAC"
    DCMI = "DCMI"
    ETH = "ETH"
    FSMC = "FSMC"
    HASH = "HASH"
    IWDG = "IWDG"
    RNG = "RNG"
    RTC = "RTC"
    SDIO = "SDIO"
    USB = "USB"
    WWDG = "WWDG"
    # 非外设
    CHAT = "CHAT"
    UNKNOWN = "UNKNOWN"


class Scene(str, Enum):
    INIT = "init"
    CONFIG = "config"
    INTERRUPT = "interrupt"
    DEINIT = "deinit"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class KnowledgeStatus(str, Enum):
    RAW = "raw"
    PROPOSED = "proposed"
    INTEGRATED = "integrated"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class RuleLevel(str, Enum):
    """规则校验等级。"""

    MUST = "MUST"
    SHOULD = "SHOULD"
    MAY = "MAY"
