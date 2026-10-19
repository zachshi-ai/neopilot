"""NeoPilot 能力目录.

把 STEPX Neo 上真实存在的原子能力（method）整理成结构化条目，供编排器引用、
驾驶舱展示与健康度统计。所有 method 均来自设备端能力探测结果，不臆造。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Dict, List


@dataclass(frozen=True)
class Capability:
    method: str
    name: str
    app: str
    category: str
    kind: str          # read / write / navigate
    risk: str          # low / medium / high
    desc: str
    params: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


CAPABILITIES: List[Capability] = [
    # ── 系统与设备 ─────────────────────────────────────────────
    Capability("settings_get_current_battery_level", "查询电池电量", "设置", "设备", "read", "low",
               "读取当前电池电量百分比", []),
    Capability("settings_adjust_brightness", "调节屏幕亮度", "设置", "设备", "write", "low",
               "相对或绝对调节屏幕亮度（1-100）", ["openState", "newValue"]),
    Capability("settings_battery_saver_switch", "省电模式开关", "设置", "设备", "write", "low",
               "直接开启或关闭省电模式", ["openState"]),
    Capability("settings_vibration_switch", "系统震动开关", "设置", "设备", "write", "low",
               "直接开启或关闭系统震动", ["openState"]),
    Capability("settings_auto_brightness_switch", "自动亮度开关", "设置", "设备", "write", "low",
               "开启或关闭自动亮度调节", ["openState"]),
    Capability("settings_bluetooth_switch", "蓝牙开关", "设置", "设备", "write", "medium",
               "直接开启或关闭蓝牙", ["openState"]),
    Capability("settings_airplane_mode_switch", "飞行模式开关", "设置", "设备", "write", "high",
               "开启或关闭飞行模式，会断开全部网络", ["openState"]),
    Capability("settings_battery_percentage_switch", "状态栏电量百分比", "设置", "设备", "write", "low",
               "显示或隐藏状态栏电量百分比", ["openState"]),
    Capability("open_flash_light", "手电筒开关", "系统界面", "设备", "write", "low",
               "打开或关闭闪光灯", ["openState"]),
    Capability("screen_capture_screenshot", "截屏", "系统界面助手", "设备", "read", "low",
               "捕获当前屏幕内容", []),
    Capability("screen_capture_record", "开始录屏", "系统界面助手", "设备", "write", "medium",
               "启动屏幕录制", []),
    Capability("screen_capture_stop_record", "停止录屏", "系统界面助手", "设备", "write", "low",
               "结束录屏并保存文件", []),
    Capability("common_ability_get_app_list", "已安装应用列表", "通用原子能力", "设备", "read", "low",
               "获取第三方应用名称与包名", []),
    Capability("show_notify_by_info", "发送系统通知", "通用原子能力", "设备", "write", "low",
               "在通知栏展示自定义通知", ["title", "content", "intent", "icon"]),
    Capability("settings_open_settings_storage_dashboard_activity", "打开存储空间管理", "设置", "设备", "navigate", "low",
               "进入存储空间使用量页面", []),
    Capability("settings_open_manage_applications", "打开应用管理", "设置", "设备", "navigate", "low",
               "查看全部已安装应用", []),
    Capability("settings_get_app_lock_state", "查询应用锁状态", "设置", "设备", "read", "low",
               "查询应用锁/应用加密开关状态", []),

    # ── 时间与日程 ─────────────────────────────────────────────
    Capability("calendar_query_event", "查询日程", "日历", "日程", "read", "low",
               "按时间区间查询日程事件", ["start_time", "end_time"]),
    Capability("calendar_add_event", "新建日程", "日历", "日程", "write", "medium",
               "创建日程，支持地点、提醒与重复规则",
               ["title", "start_time", "end_time", "location", "reminder_offset", "recurrence_type"]),
    Capability("calendar_edit_event", "编辑日程", "日历", "日程", "write", "medium",
               "修改已有日程的时间或标题", ["start_time", "end_time", "title"]),
    Capability("calendar_delete_event", "删除日程", "日历", "日程", "write", "high",
               "删除匹配到的日程，重复日程按整条系列删除", ["start_time", "end_time", "title"]),
    Capability("calendar_add_special_event", "新建纪念日", "日历", "日程", "write", "medium",
               "创建生日 / 纪念日 / 倒数日", ["type", "title", "date_time"]),
    Capability("alarm_clock_add", "新建闹钟", "时钟", "日程", "write", "medium",
               "创建闹钟，支持重复与震动", ["hour", "minute", "label", "repeatDays", "weekdays"]),
    Capability("alarm_clock_timer_add", "启动倒计时", "时钟", "日程", "write", "low",
               "按秒数启动倒计时计时器", ["seconds", "label"]),

    # ── 位置 · 天气 · 出行 ─────────────────────────────────────
    Capability("get_current_location", "获取当前位置", "XMSCore", "位置", "read", "medium",
               "返回 WGS84 经纬度与文字地址", []),
    Capability("weather_get_current_location_weather", "本地天气", "天气", "天气", "read", "low",
               "端内自动定位，返回逐日或逐时预报与生活指数",
               ["type", "startDate", "endDate", "startHour"]),
    Capability("get_weather", "指定城市天气", "云端天气服务", "天气", "read", "low",
               "按省市区查询未来 15 天天气", ["province", "city", "area", "type", "startDate", "endDate"]),
    Capability("amap_route_card", "路线卡", "高德", "出行", "read", "low",
               "并发返回驾车 / 步行 / 骑行的耗时与距离", ["origin", "destination", "mode"]),
    Capability("amap_overview_card", "周边概览卡", "高德", "出行", "read", "low",
               "搜索周边地点并出地图概览卡", ["keywords", "location", "radius", "city", "limit"]),
    Capability("maps_direction_transit_integrated", "公交地铁方案", "高德云端MCP", "出行", "read", "low",
               "返回公交换乘方案", ["origin", "destination", "city", "cityd"]),
    Capability("maps_regeocode", "逆地理编码", "高德云端MCP", "位置", "read", "low",
               "经纬度转行政区划", ["location"]),
    Capability("maps_schema_personal_map", "多点标图", "高德云端MCP", "出行", "read", "low",
               "把多个地点标到高德地图", ["orgName", "lineList", "sceneType"]),

    # ── 媒体与文件 ─────────────────────────────────────────────
    Capability("gallery_intelligent_search", "相册语义搜索", "图库", "媒体", "read", "low",
               "用自然语言在本地相册做语义检索", ["search_content", "countLimit"]),
    Capability("gallery_local_search", "相册结构化搜索", "图库", "媒体", "read", "low",
               "按时间 / 地点 / 人物 / 场景 / OCR 组合检索", ["start_time", "end_time", "people", "scenes", "ocr_texts"]),
    Capability("gallery_move_media_to_album", "移入相册", "图库", "媒体", "write", "medium",
               "把媒体文件移动到指定相册", ["filePath", "albumName"]),
    Capability("gallery_create_album", "新建相册", "图库", "媒体", "write", "low",
               "创建自定义名称相册", ["albumName"]),
    Capability("filemanager_create_file", "新建文件", "文件管理", "文件", "write", "medium",
               "在指定目录创建空文件", ["fileName", "folderPath"]),
    Capability("filemanager_create_folder", "新建文件夹", "文件管理", "文件", "write", "low",
               "在内部存储根目录创建文件夹", ["folderName"]),
    Capability("filemanager_get_screen_recording_file_list", "录屏文件列表", "文件管理", "文件", "read", "low",
               "获取录屏文件清单", []),
    Capability("lite_recorder_open_recording", "快记录音", "快记", "媒体", "write", "medium",
               "打开快记并开始录音", []),

    # ── 通信与权限 ─────────────────────────────────────────────
    Capability("sms_open_notice_list", "通知类短信", "信息", "通信", "navigate", "medium",
               "打开验证码 / 快递 / 账单等通知短信列表", []),
    Capability("security_permissioncontroller_global_location", "定位总开关", "权限控制器", "权限", "write", "high",
               "控制系统级定位开关，影响所有应用", ["enable"]),
]


_BY_METHOD: Dict[str, Capability] = {c.method: c for c in CAPABILITIES}


def get(method: str) -> Capability:
    return _BY_METHOD[method]


def exists(method: str) -> bool:
    return method in _BY_METHOD


def all_caps() -> List[Capability]:
    return list(CAPABILITIES)


def categories() -> Dict[str, List[Capability]]:
    out: Dict[str, List[Capability]] = {}
    for c in CAPABILITIES:
        out.setdefault(c.category, []).append(c)
    return out


def stats() -> Dict[str, int]:
    s = {"total": len(CAPABILITIES)}
    for c in CAPABILITIES:
        s[c.kind] = s.get(c.kind, 0) + 1
        s["risk_" + c.risk] = s.get("risk_" + c.risk, 0) + 1
    return s
