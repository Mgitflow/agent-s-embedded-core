"""功能级工艺契约：每个功能模板声明「该产出什么」的代码特征。

这是念安核心诉求的落地——**工艺监测的功能级标准答案**：
识别到「点灯」，生成的代码里就必须有 GPIO 初始化 + TogglePin；
识别到「按键」，就必须有 GPIO 初始化 + ReadPin；
识别到「串口打印」，就必须有 UART Init + Transmit。

监测器据此做「功能级静态审查加孔」：每个被识别的功能，其 must_have
调用是否都在生成代码里。缺失 = 该功能「钉错了孔」（生成偏了）。

must_have 分两级：
  - must_calls：必须出现的 HAL 调用（核心功能调用，缺了功能就不成立）
  - must_init：必须出现的初始化调用（缺了外设没配置）

来源：功能模板 init/loop/deinit 三段中，去掉通用（HAL_Delay/HAL_OK/DeInit/
RCC 时钟使能）后，剩下的「功能性」调用。
"""

from __future__ import annotations

from typing import Any

# 功能模板 → 必须出现的核心 HAL 调用（识别到该功能，代码里就必须有这些）
# 通用调用已剔除：HAL_Delay（延时非功能性）、HAL_OK（返回值宏）、*_DeInit（反初始化）、
# __HAL_RCC_*（时钟使能，属于骨架非功能）。

PROCESS_CONTRACT: dict[str, dict[str, Any]] = {
    "led_blink": {
        "must_calls": ["HAL_GPIO_Init", "HAL_GPIO_TogglePin"],
        "peripheral": "GPIO",
        "desc": "点灯（GPIO 推挽输出 + 翻转）",
    },
    "gpio_multi_out": {
        "must_calls": ["HAL_GPIO_Init", "HAL_GPIO_WritePin"],
        "peripheral": "GPIO",
        "desc": "多引脚输出",
    },
    "button_read": {
        "must_calls": ["HAL_GPIO_Init", "HAL_GPIO_ReadPin"],
        "peripheral": "GPIO",
        "desc": "按键读取（输入 + 读电平）",
    },
    "gpio_exti": {
        "must_calls": ["HAL_GPIO_Init", "HAL_NVIC_EnableIRQ", "HAL_GPIO_EXTI_Callback"],
        "peripheral": "GPIO",
        "desc": "外部中断",
    },
    "uart_print": {
        "must_calls": ["HAL_UART_Init", "HAL_UART_Transmit"],
        "peripheral": "UART",
        "desc": "串口打印",
    },
    "uart_interrupt": {
        "must_calls": ["HAL_UART_Init", "HAL_UART_Receive_IT", "HAL_UART_RxCpltCallback"],
        "peripheral": "UART",
        "desc": "串口中断接收",
    },
    "uart_dma": {
        "must_calls": ["HAL_UART_Init", "HAL_UART_Transmit_DMA"],
        "peripheral": "UART",
        "desc": "串口 DMA 发送",
    },
    "spi_master": {
        "must_calls": ["HAL_SPI_Init", "HAL_SPI_TransmitReceive"],
        "peripheral": "SPI",
        "desc": "SPI 主模式收发",
    },
    "i2c_scan": {
        "must_calls": ["HAL_I2C_Init", "HAL_I2C_IsDeviceReady"],
        "peripheral": "I2C",
        "desc": "I2C 设备扫描",
    },
    "i2c_sensor": {
        "must_calls": ["HAL_I2C_Init", "HAL_I2C_Mem_Read"],
        "peripheral": "I2C",
        "desc": "I2C 传感器读取",
    },
    "adc_read": {
        "must_calls": ["HAL_ADC_Init", "HAL_ADC_Start", "HAL_ADC_GetValue"],
        "peripheral": "ADC",
        "desc": "ADC 单次采样",
    },
    "adc_dma_scan": {
        "must_calls": ["HAL_ADC_Init", "HAL_ADC_Start_DMA", "HAL_DMA_Init"],
        "peripheral": "ADC",
        "desc": "ADC DMA 连续扫描",
    },
    "dac_output": {
        "must_calls": ["HAL_DAC_Init", "HAL_DAC_Start", "HAL_DAC_SetValue"],
        "peripheral": "DAC",
        "desc": "DAC 模拟输出",
    },
    "dma_mem_copy": {
        "must_calls": ["HAL_DMA_Init", "HAL_DMA_Start"],
        "peripheral": "DMA",
        "desc": "DMA 内存搬运",
    },
    "can_communication": {
        "must_calls": ["HAL_CAN_Init", "HAL_CAN_Start", "HAL_CAN_AddTxMessage"],
        "peripheral": "CAN",
        "desc": "CAN 通信",
    },
    "rtc_calendar": {
        "must_calls": ["HAL_RTC_Init", "HAL_RTC_GetTime"],
        "peripheral": "RTC",
        "desc": "RTC 日历",
    },
    "crc_compute": {
        "must_calls": ["HAL_CRC_Init", "HAL_CRC_Calculate"],
        "peripheral": "CRC",
        "desc": "CRC 校验计算",
    },
    "rng_random": {
        "must_calls": ["HAL_RNG_Init", "HAL_RNG_GenerateRandomNumber"],
        "peripheral": "RNG",
        "desc": "随机数生成",
    },
    "iwdg_refresh": {
        "must_calls": ["HAL_IWDG_Init", "HAL_IWDG_Refresh"],
        "peripheral": "IWDG",
        "desc": "独立看门狗喂狗",
    },
    "wwdg_refresh": {
        "must_calls": ["HAL_WWDG_Init", "HAL_WWDG_Refresh"],
        "peripheral": "WWDG",
        "desc": "窗口看门狗喂狗",
    },
    "system_reset": {
        "must_calls": ["HAL_IWDG_Init"],
        "peripheral": "IWDG",
        "desc": "系统复位（看门狗触发）",
    },
    "tim_periodic": {
        "must_calls": ["HAL_TIM_Base_Init", "HAL_TIM_Base_Start_IT", "HAL_TIM_PeriodElapsedCallback"],
        "peripheral": "TIM",
        "desc": "定时器周期中断",
    },
    "tim_input_capture": {
        "must_calls": ["HAL_TIM_IC_Init", "HAL_TIM_IC_Start_IT", "HAL_TIM_ReadCapturedValue"],
        "peripheral": "TIM",
        "desc": "定时器输入捕获",
    },
    "pwm_output": {
        "must_calls": ["HAL_TIM_PWM_Init", "HAL_TIM_PWM_Start", "HAL_TIM_PWM_ConfigChannel"],
        "peripheral": "TIM",
        "desc": "PWM 输出",
    },
    "pwm_servo": {
        "must_calls": ["HAL_TIM_PWM_Init", "HAL_TIM_PWM_Start", "HAL_TIM_PWM_ConfigChannel"],
        "peripheral": "TIM",
        "desc": "舵机 PWM 控制",
    },
    "sd_card": {
        "must_calls": ["HAL_SD_Init", "HAL_SD_ReadBlocks"],
        "peripheral": "SDIO",
        "desc": "SD 卡读写",
    },
    "usb_init": {
        "must_calls": ["HAL_PCD_Init", "HAL_PCD_Start"],
        "peripheral": "USB",
        "desc": "USB 设备初始化（PCD）",
    },
}


def check_feature(code: str, must_calls: list[str]) -> tuple[bool, list[str]]:
    """校验一段生成代码是否含指定功能模板的全部 must_calls。返回 (是否齐全, 缺失项)。"""
    missing = [c for c in must_calls if c not in code]
    return (not missing), missing


def check_requirements(
    code: str, template_ids: list[str]
) -> dict[str, Any]:
    """功能级工艺监测：对每个被识别功能，校验其 must_calls 是否都在代码里。

    Returns:
        {"led_blink": {"ok": bool, "missing": [...]}, ..., "_all_ok": bool}
    """
    report: dict[str, Any] = {}
    for tid in template_ids:
        contract = PROCESS_CONTRACT.get(tid)
        if contract is None:
            report[tid] = {"ok": True, "missing": [], "note": "无工艺契约（未登记）"}
            continue
        ok, missing = check_feature(code, contract["must_calls"])
        report[tid] = {"ok": ok, "missing": missing, "peripheral": contract["peripheral"]}
    report["_all_ok"] = all(
        v["ok"] for k, v in report.items() if k != "_all_ok"
    )
    return report
