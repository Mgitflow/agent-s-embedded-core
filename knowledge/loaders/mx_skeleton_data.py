"""骨架模板数据：集中管理 MxSkeleton 使用的 F407 寄存器默认值、F4 内存映射与工具版本等常量，纯数据无业务逻辑。"""
from pathlib import Path

# ===== F407 默认寄存器值（从 fcnt_notes.py 合并）=====
F407_DEFAULTS = {
    "flash_latency": "FLASH_LATENCY_5",
    "voltage_scale": "PWR_REGULATOR_VOLTAGE_SCALE1",
    "pll_m": 8,
    "pll_n": 336,
    "pll_p": "RCC_PLLP_DIV2",
    "pll_q": 7,
    "hse_value": 8000000,
    "sysclk_hz": 168000000,
}

F407_CLOCK_NOTES = """  * Clock Configuration (STM32F407/APM32F407, 168MHz):
  *   HSE = 8MHz → PLL (M=8, N=336, P=2, Q=7) → SYSCLK = 168MHz
  *   AHB  = 168MHz (HCLK)
  *   APB1 = 42MHz  (PCLK1 = HCLK/4)
  *   APB2 = 84MHz  (PCLK2 = HCLK/2)
  *   TIM on APB1: ×2 → 84MHz | TIM on APB2: ×2 → 168MHz"""


def _tool_version() -> str:
    """从 pyproject.toml 动态读取项目版本号。"""
    try:
        pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
        with open(pyproject, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except (OSError, ValueError):
        pass
    return "1.0.0"


# ===== HAL 模块宏配置 =====
# 某些 HAL 头文件会引用其他模块的类型定义
HAL_MODULE_DEPENDENCIES: dict[str, set[str]] = {
    "HAL_DAC_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_ADC_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_I2C_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_SPI_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_UART_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_USART_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_TIM_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_ETH_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED"},
    "HAL_SD_MODULE_ENABLED": {"HAL_DMA_MODULE_ENABLED", "HAL_GPIO_MODULE_ENABLED"},
    "HAL_PCD_MODULE_ENABLED": {"HAL_GPIO_MODULE_ENABLED"},
    "HAL_HCD_MODULE_ENABLED": {"HAL_GPIO_MODULE_ENABLED"},
}

# 外设名 → HAL 模块宏映射（外设名与 HAL 模块名不完全一致时转换）
PERIPHERAL_TO_HAL_MODULES: dict[str, set[str]] = {
    "USB": {"HAL_PCD_MODULE_ENABLED", "HAL_HCD_MODULE_ENABLED"},
    "SDIO": {"HAL_SD_MODULE_ENABLED"},
}

# 任何工程都必须启用的基础 HAL 模块宏
ALWAYS_ENABLED_HAL_MODULES: set[str] = {
    "HAL_MODULE_ENABLED",
    "HAL_RCC_MODULE_ENABLED",
    "HAL_GPIO_MODULE_ENABLED",
    "HAL_CORTEX_MODULE_ENABLED",
    "HAL_PWR_MODULE_ENABLED",
    "HAL_EXTI_MODULE_ENABLED",
    "HAL_FLASH_MODULE_ENABLED",
}

# ETH 启用时需在 hal_conf.h 末尾注入的 PHY 基础宏定义
PHY_MACRO_DEFS = """
/* PHY 基础宏定义（ETH HAL 依赖） */
#define PHY_READ_TO                     0x0000FFFFU
#define PHY_WRITE_TO                    0x0000FFFFU
#define PHY_RESET_DELAY                 0x000000FFU
#define PHY_CONFIG_DELAY                0x00000FFFU
#define PHY_BCR                         ((uint16_t)0x0000)
#define PHY_BSR                         ((uint16_t)0x0001)
#define PHY_RESET                       ((uint16_t)0x8000)
#define PHY_AUTONEGOTIATION             ((uint16_t)0x1000)
#define PHY_LINK_STATUS                 ((uint16_t)0x0001)
#define PHY_SPEED_STATUS                ((uint16_t)0x0002)
#define PHY_DUPLEX_STATUS               ((uint16_t)0x0004)
"""
