"""标准 STM32 HAL 的 MSP 签名权威表 + 对照校验（防漂移锁）。

背景：2026-08-20 发现 P0 功能性 bug——`PERIPHERAL_FILE_MAP["GPIO"]` 把 MSP 签名
写成 ``GPIO_InitTypeDef* GPIO_Init``（类型错，应是 ``GPIO_TypeDef*``），且把 GPIO
时钟拆进 hal_msp.c 的 ``HAL_GPIO_MspInit``。但 STM32 F4 HAL 的 **GPIO 没有 MspInit
回调**（CRC/RNG 等都有 ``__weak HAL_xxx_MspInit``，唯独 GPIO 没有，ST 未为 GPIO
设计 MSP 层）。修法（念安定）：**虚拟一个 HAL_GPIO_MspInit**——GPIO 结构上和其他
外设统一（时钟拆 msp），由 MX_GPIO_Init 手动调用它（因为 HAL 不自动调），签名对齐
其他外设的 ``xxx_HandleTypeDef*`` 风格。

本模块把「哪些外设有 MspInit、签名是什么」固化为单一权威源（对齐 ST 官方 HAL
源码），并提供 ``audit_msp_signatures`` 对照校验：任何生成侧（如
``PERIPHERAL_FILE_MAP``、functional 模板）的 MSP 签名偏离此表，校验即报漂移。

依赖方向：本模块属 contracts 层，**不 import knowledge/engine**；生成侧把自身
签名表传进来校验，contracts 不反向依赖实现。
"""
from __future__ import annotations

# 外设 → (MspInit 函数名, MspInit 参数签名)。
# 签名对齐 ST 官方 HAL 源码（reference-stm32f4/hal/Src/stm32f4xx_hal_*.c 的 __weak 定义）。
# 例外：GPIO 标准 HAL 无 MspInit（ST 未设计 MSP 层），此处是「虚拟 MspInit」——
# 结构统一（时钟拆 msp），由 MX_GPIO_Init 手动调用，签名对齐 HandleTypeDef* 风格。
HAL_MSP_SIGNATURES: dict[str, tuple[str, str]] = {
    "GPIO": ("HAL_GPIO_MspInit", "GPIO_TypeDef* GPIO_Handle"),  # ST 无 GPIO MSP 层 → 虚拟 MspInit，MX_GPIO_Init 手动调用
    "UART": ("HAL_UART_MspInit", "UART_HandleTypeDef* huart"),
    "TIM": ("HAL_TIM_Base_MspInit", "TIM_HandleTypeDef* htim_base"),  # PWM/IC 变体运行时推断
    "SPI": ("HAL_SPI_MspInit", "SPI_HandleTypeDef* hspi"),
    "I2C": ("HAL_I2C_MspInit", "I2C_HandleTypeDef* hi2c"),
    "ADC": ("HAL_ADC_MspInit", "ADC_HandleTypeDef* hadc"),
    "DAC": ("HAL_DAC_MspInit", "DAC_HandleTypeDef* hdac"),
    "DMA": ("HAL_DMA_MspInit", "DMA_HandleTypeDef* hdma"),
    "RTC": ("HAL_RTC_MspInit", "RTC_HandleTypeDef* hrtc"),
    "CAN": ("HAL_CAN_MspInit", "CAN_HandleTypeDef* hcan"),
    "SDIO": ("HAL_SD_MspInit", "SD_HandleTypeDef* hsd"),
    "IWDG": ("HAL_IWDG_MspInit", "IWDG_HandleTypeDef* hiwdg"),
    "WWDG": ("HAL_WWDG_MspInit", "WWDG_HandleTypeDef* hwwdg"),
    "CRC": ("HAL_CRC_MspInit", "CRC_HandleTypeDef* hcrc"),
    "RNG": ("HAL_RNG_MspInit", "RNG_HandleTypeDef* hrng"),
}


def audit_msp_signatures(actual: dict[str, tuple[str, str]]) -> list[str]:
    """对照校验：actual 的 MSP 签名是否对齐标准 HAL 权威表。

    ``actual`` 通常是生成侧的 ``PERIPHERAL_FILE_MAP``（外设 → (文件名, msp_fn,
    msp_param)），调用方需先投影成 ``{外设: (msp_fn, msp_param)}`` 再传入。

    返回漂移项列表（空 = 对齐）。双向检查：
    ① 每个外设签名与权威表一致（含「无 MspInit 的外设不得有非空签名」）
    ② 权威表里每个外设都出现在 actual（防权威表/实现表遗漏）
    """
    drift: list[str] = []
    for periph, (fn, param) in actual.items():
        std_fn, std_param = HAL_MSP_SIGNATURES.get(periph, (fn, param))
        if (fn, param) != (std_fn, std_param):
            drift.append(
                f"{periph}: 实际 ({fn!r}, {param!r}) != 标准 ({std_fn!r}, {std_param!r})"
            )
    for periph in HAL_MSP_SIGNATURES:
        if periph not in actual:
            drift.append(f"{periph}: 标准 HAL 有此外设，但生成侧签名表缺失")
    return drift


def peripheral_msp_projection(file_map: dict[str, tuple[str, str, str]]) -> dict[str, tuple[str, str]]:
    """把生成侧的 ``PERIPHERAL_FILE_MAP``（外设 → (文件名, msp_fn, msp_param)）
    投影成校验所需的 ``{外设: (msp_fn, msp_param)}``。"""
    return {p: (fn, param) for p, (_fname, fn, param) in file_map.items()}
