import enum
import logging
import re
from typing import Any, Dict, Optional

import click

from .click_common import EnumType, command, format_output
from .device import DeviceException
from .miot_device import MiotDevice

_LOGGER = logging.getLogger(__name__)


class AirPurifierMiotException(DeviceException):
    pass


class OperationMode(enum.Enum):
    Auto = 0
    Silent = 1
    Favorite = 2
    Fan = 3


class LedBrightness(enum.Enum):
    Bright = 0
    Dim = 1
    Off = 2


class FilterType(enum.Enum):
    Regular = "regular"
    AntiBacterial = "anti-bacterial"
    AntiFormaldehyde = "anti-formaldehyde"
    Unknown = "unknown"


FILTER_TYPE_RE = (
    (re.compile(r"^\d+:\d+:41:30$"), FilterType.AntiBacterial),
    (re.compile(r"^\d+:\d+:(30|0|00):31$"), FilterType.AntiFormaldehyde),
    (re.compile(r".*"), FilterType.Regular),
)


class AirPurifierMiotStatus:
    """Container for status reports from the air purifier."""

    _filter_type_cache = {}

    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data

    @property
    def is_on(self) -> bool:
        """Return True if device is on."""
        return self.data["power"]

    @property
    def power(self) -> str:
        """Power state."""
        return "on" if self.is_on else "off"

    @property
    def aqi(self) -> int:
        """Air quality index."""
        return self.data["aqi"]

    @property
    def average_aqi(self) -> int:
        """Average of the air quality index."""
        return self.data["average_aqi"]

    @property
    def humidity(self) -> int:
        """Current humidity."""
        return self.data["humidity"]

    @property
    def temperature(self) -> Optional[float]:
        """Current temperature, if available."""
        if self.data["temperature"] is not None:
            return self.data["temperature"]

        return None

    @property
    def fan_level(self) -> int:
        """Current fan level."""
        return self.data["fan_level"]

    @property
    def mode(self) -> OperationMode:
        """Current operation mode."""
        return OperationMode(self.data["mode"])

    @property
    def led(self) -> bool:
        """Return True if LED is on."""
        return self.data["led"]

    @property
    def led_brightness(self) -> Optional[LedBrightness]:
        """Brightness of the LED."""
        if self.data["led_brightness"] is not None:
            try:
                return LedBrightness(self.data["led_brightness"])
            except ValueError:
                return None

        return None

    @property
    def buzzer(self) -> Optional[bool]:
        """Return True if buzzer is on."""
        if self.data["buzzer"] is not None:
            return self.data["buzzer"]

        return None

    @property
    def child_lock(self) -> bool:
        """Return True if child lock is on."""
        return self.data["child_lock"]

    @property
    def favorite_level(self) -> int:
        """Return favorite level, which is used if the mode is ``favorite``."""
        # Favorite level used when the mode is `favorite`.
        return self.data["favorite_level"]

    @property
    def filter_life_remaining(self) -> int:
        """Time until the filter should be changed."""
        return self.data["filter_life_remaining"]

    @property
    def filter_hours_used(self) -> int:
        """How long the filter has been in use."""
        return self.data["filter_hours_used"]

    @property
    def use_time(self) -> int:
        """How long the device has been active in seconds."""
        return self.data["use_time"]

    @property
    def purify_volume(self) -> int:
        """The volume of purified air in cubic meter."""
        return self.data["purify_volume"]

    @property
    def motor_speed(self) -> int:
        """Speed of the motor."""
        return self.data["motor_speed"]

    @property
    def filter_rfid_product_id(self) -> Optional[str]:
        """RFID product ID of installed filter."""
        return self.data["filter_rfid_product_id"]

    @property
    def filter_rfid_tag(self) -> Optional[str]:
        """RFID tag ID of installed filter."""
        return self.data["filter_rfid_tag"]

    @property
    def filter_type(self) -> Optional[FilterType]:
        """Type of installed filter."""
        if self.filter_rfid_tag is None:
            return None
        if self.filter_rfid_tag == "0:0:0:0:0:0:0":
            return FilterType.Unknown
        if self.filter_rfid_product_id is None:
            return FilterType.Regular
        return self._get_filter_type(self.filter_rfid_product_id)

    @property
    def button_pressed(self) -> Optional[str]:
        """Last pressed button."""
        return self.data["button_pressed"]

    @classmethod
    def _get_filter_type(cls, product_id: str) -> FilterType:
        ft = cls._filter_type_cache.get(product_id, None)
        if ft is None:
            for filter_re, filter_type in FILTER_TYPE_RE:
                if filter_re.match(product_id):
                    ft = cls._filter_type_cache[product_id] = filter_type
                    break
        return ft

    def __repr__(self) -> str:
        s = (
            "<AirPurifierMiotStatus power=%s, "
            "aqi=%s, "
            "average_aqi=%s, "
            "temperature=%s, "
            "humidity=%s%%, "
            "fan_level=%s, "
            "mode=%s, "
            "led=%s, "
            "led_brightness=%s, "
            "buzzer=%s, "
            "child_lock=%s, "
            "favorite_level=%s, "
            "filter_life_remaining=%s, "
            "filter_hours_used=%s, "
            "use_time=%s, "
            "purify_volume=%s, "
            "motor_speed=%s, "
            "filter_rfid_product_id=%s, "
            "filter_rfid_tag=%s, "
            "filter_type=%s>"
            % (
                self.power,
                self.aqi,
                self.average_aqi,
                self.temperature,
                self.humidity,
                self.fan_level,
                self.mode,
                self.led,
                self.led_brightness,
                self.buzzer,
                self.child_lock,
                self.favorite_level,
                self.filter_life_remaining,
                self.filter_hours_used,
                self.use_time,
                self.purify_volume,
                self.motor_speed,
                self.filter_rfid_product_id,
                self.filter_rfid_tag,
                self.filter_type,
            )
        )
        return s

    def __json__(self):
        return self.data


class AirPurifierMiot(MiotDevice):
    """Main class representing the air purifier which uses MIoT protocol."""

    def __init__(
        self,
        ip: str = None,
        token: str = None,
        start_id: int = 0,
        debug: int = 0,
        lazy_discover: bool = True,
    ) -> None:
        super().__init__(
            {
                # Air Purifier (siid=2)
                "power": {"siid": 2, "piid": 2},
                "fan_level": {"siid": 2, "piid": 4},
                "mode": {"siid": 2, "piid": 5},
                # Environment (siid=3)
                "humidity": {"siid": 3, "piid": 7},
                "temperature": {"siid": 3, "piid": 8},
                "aqi": {"siid": 3, "piid": 6},
                # Filter (siid=4)
                "filter_life_remaining": {"siid": 4, "piid": 3},
                "filter_hours_used": {"siid": 4, "piid": 5},
                # Alarm (siid=5)
                "buzzer": {"siid": 5, "piid": 1},
                # Indicator Light (siid=6)
                "led_brightness": {"siid": 6, "piid": 1},
                "led": {"siid": 6, "piid": 6},
                # Physical Control Locked (siid=7)
                "child_lock": {"siid": 7, "piid": 1},
                # Motor Speed (siid=10)
                "favorite_level": {"siid": 10, "piid": 10},
                "motor_speed": {"siid": 10, "piid": 8},
                # Use time (siid=12)
                "use_time": {"siid": 12, "piid": 1},
                # AQI (siid=13)
                "purify_volume": {"siid": 13, "piid": 1},
                "average_aqi": {"siid": 13, "piid": 2},
                # RFID (siid=14)
                "filter_rfid_tag": {"siid": 14, "piid": 1},
                "filter_rfid_product_id": {"siid": 14, "piid": 3},
                # Other (siid=15)
                "app_extra": {"siid": 15, "piid": 1},
            },
            ip,
            token,
            start_id,
            debug,
            lazy_discover,
        )

    @command(
        default_output=format_output(
            "",
            "Power: {result.power}\n"
            "AQI: {result.aqi} μg/m³\n"
            "Average AQI: {result.average_aqi} μg/m³\n"
            "Humidity: {result.humidity} %\n"
            "Temperature: {result.temperature} °C\n"
            "Fan Level: {result.fan_level}\n"
            "Mode: {result.mode}\n"
            "LED: {result.led}\n"
            "LED brightness: {result.led_brightness}\n"
            "Buzzer: {result.buzzer}\n"
            "Child lock: {result.child_lock}\n"
            "Favorite level: {result.favorite_level}\n"
            "Filter life remaining: {result.filter_life_remaining} %\n"
            "Filter hours used: {result.filter_hours_used}\n"
            "Use time: {result.use_time} s\n"
            "Purify volume: {result.purify_volume} m³\n"
            "Motor speed: {result.motor_speed} rpm\n"
            "Filter RFID product id: {result.filter_rfid_product_id}\n"
            "Filter RFID tag: {result.filter_rfid_tag}\n"
            "Filter type: {result.filter_type}\n",
        )
    )
    def status(self) -> AirPurifierMiotStatus:
        """Retrieve properties."""

        return AirPurifierMiotStatus(
            {prop["did"]: prop["value"] for prop in self.get_properties()}
        )

    @command(default_output=format_output("Powering on"))
    def on(self):
        """Power on."""
        return self.set_property("power", True)

    @command(default_output=format_output("Powering off"))
    def off(self):
        """Power off."""
        return self.set_property("power", False)

    @command(
        click.argument("level", type=int),
        default_output=format_output("Setting fan level to '{level}'"),
    )
    def set_fan_level(self, level: int):
        """Set fan level."""
        if level < 1 or level > 3:
            raise AirPurifierMiotException("Invalid fan level: %s" % level)
        return self.set_property("fan_level", level)

    @command(
        click.argument("mode", type=EnumType(OperationMode, False)),
        default_output=format_output("Setting mode to '{mode.value}'"),
    )
    def set_mode(self, mode: OperationMode):
        """Set mode."""
        return self.set_property("mode", mode.value)

    @command(
        click.argument("level", type=int),
        default_output=format_output("Setting favorite level to {level}"),
    )
    def set_favorite_level(self, level: int):
        """Set favorite level."""
        if level < 0 or level > 14:
            raise AirPurifierMiotException("Invalid favorite level: %s" % level)

        # Set the favorite level used when the mode is `favorite`,
        # should be  between 0 and 14.
        return self.set_property("favorite_level", level)

    @command(
        click.argument("brightness", type=EnumType(LedBrightness, False)),
        default_output=format_output("Setting LED brightness to {brightness}"),
    )
    def set_led_brightness(self, brightness: LedBrightness):
        """Set led brightness."""
        return self.set_property("led_brightness", brightness.value)

    @command(
        click.argument("led", type=bool),
        default_output=format_output(
            lambda led: "Turning on LED" if led else "Turning off LED"
        ),
    )
    def set_led(self, led: bool):
        """Turn led on/off."""
        return self.set_property("led", led)

    @command(
        click.argument("buzzer", type=bool),
        default_output=format_output(
            lambda buzzer: "Turning on buzzer" if buzzer else "Turning off buzzer"
        ),
    )
    def set_buzzer(self, buzzer: bool):
        """Set buzzer on/off."""
        return self.set_property("buzzer", buzzer)

    @command(
        click.argument("lock", type=bool),
        default_output=format_output(
            lambda lock: "Turning on child lock" if lock else "Turning off child lock"
        ),
    )
    def set_child_lock(self, lock: bool):
        """Set child lock on/off."""
        return self.set_property("child_lock", lock)