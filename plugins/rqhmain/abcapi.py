#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABC API 工具集合
包含：天气查询、新闻获取、数字转中文、文字转图片等功能
"""

import os
import re
import json
import time
import hashlib
import urllib.parse
import requests
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Optional, Tuple, List, Union
from pathlib import Path


# 单次 HTTP 请求超时。原为 10s：在异步处理器中阻塞调用时，
# 一次超时就会冻结整个事件循环 10s，故收紧到 5s 以限制最坏情况。
HTTP_TIMEOUT_SECONDS = 5


class WeatherAPI:
    """天气查询API"""
    
    def __init__(self, base_url: str = "https://api.52vmy.cn/api/query/tian/three"):
        self.base_url = base_url
    
    def query_weather(self, city: str, info_type: str = "weather") -> Dict:
        """
        查询天气信息
        
        Args:
            city: 城市名称
            info_type: 信息类型 (weather/forecast)
        
        Returns:
            包含天气信息的字典
        """
        try:
            url = f"{self.base_url}?city={city}&type={info_type}"
            response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            
            try:
                data = response.json()
                return {
                    "success": True,
                    "city": city,
                    "type": info_type,
                    "data": data
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "city": city,
                    "type": info_type,
                    "data": response.text
                }
                
        except requests.RequestException as e:
            return {
                "success": False,
                "city": city,
                "type": info_type,
                "error": str(e)
            }
    
    def get_current_weather(self, city: str) -> Dict:
        """获取当前天气"""
        return self.query_weather(city, "weather")
    
    def get_weather_forecast(self, city: str) -> Dict:
        """获取天气预报"""
        return self.query_weather(city, "forecast")


class NewsAPI:
    """60秒新闻API"""
    
    def __init__(self, token: Optional[str] = None):
        self.api_url = "https://api.52vmy.cn/api/wl/60s/new"
        self.token = token
        self.headers = {}
        
        if token:
            self.headers['Authorization'] = f'Bearer {token}'
    
    def get_news(self) -> Optional[Dict]:
        """
        获取60秒新闻
        
        Returns:
            字典格式的新闻数据，失败返回None
        """
        try:
            response = requests.get(
                self.api_url,
                headers=self.headers,
                timeout=HTTP_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"请求失败，状态码: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"请求出错: {e}")
            return None
    
    def set_token(self, token: str):
        """设置API token"""
        self.token = token
        self.headers['Authorization'] = f'Bearer {token}'
    
    def save_to_file(self, data: Dict, filename: str = "news.json"):
        """保存新闻数据到文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class NumberToChineseAPI:
    """数字转中文API"""
    
    def __init__(self):
        self.digits = '零一二三四五六七八九'
        self.units = ['', '十', '百', '千']
        self.big_units = ['', '万', '亿', '兆', '京', '垓', '秭', '穰', '沟', '涧', '正', '载']
    
    def convert(self, num) -> str:
        """
        将数字转换为中文读法
        
        Args:
            num: 数字（int/float/str）
        
        Returns:
            中文读法字符串
        """
        if isinstance(num, str):
            num = num.strip()
            if not num:
                raise ValueError("输入不能为空")
            
            if 'e' in num.lower():
                try:
                    num_float = float(num)
                    num = f"{num_float:.15f}".rstrip('0').rstrip('.')
                except ValueError:
                    raise ValueError("无效的数字格式")
            
            if '.' in num:
                return self._convert_float(num)
            else:
                if not num.lstrip('-').lstrip('+').isdigit():
                    raise ValueError("无效的整数格式")
                return self._convert_integer(num)
        
        elif isinstance(num, (int, float)):
            if isinstance(num, int):
                return self._convert_integer(str(num))
            else:
                num_str = f"{num:.15f}".rstrip('0').rstrip('.')
                return self._convert_float(num_str)
        else:
            raise TypeError("输入类型不支持，请传入 int、float 或 str")
    
    def _convert_integer(self, num_str: str) -> str:
        """转换整数部分"""
        if num_str.startswith('-'):
            return "负" + self._convert_positive_integer(num_str[1:])
        
        num_str = num_str.lstrip('0')
        if not num_str:
            return "零"
            
        return self._convert_positive_integer(num_str)
    
    def _convert_float(self, num_str: str) -> str:
        """转换小数"""
        if 'e' in num_str.lower():
            try:
                num_float = float(num_str)
                num_str = f"{num_float:.15f}".rstrip('0').rstrip('.')
            except ValueError:
                raise ValueError("无效的科学计数法格式")
        
        if '.' in num_str:
            parts = num_str.split('.')
            integer_part = parts[0]
            decimal_part = parts[1]
            
            integer_chinese = self._convert_integer(integer_part)
            decimal_chinese = ''.join(self.digits[int(d)] for d in decimal_part if d.isdigit())
            return f"{integer_chinese}点{decimal_chinese}"
        else:
            return self._convert_integer(num_str)
    
    def _convert_positive_integer(self, num_str: str) -> str:
        """转换正整数"""
        if num_str == "0":
            return "零"
        
        if len(num_str) > 36:
            raise ValueError(f"数字过长，最大支持36位数，当前为{len(num_str)}位")
        
        result = ""
        group = 0
        
        for i in range(len(num_str), 0, -4):
            start = max(0, i - 4)
            section_str = num_str[start:i]
            section_num = int(section_str) if section_str else 0
            
            if section_num != 0:
                section_chinese = self._convert_section(section_num)
                if group > 0:
                    section_chinese += self.big_units[group]
                result = section_chinese + result
            elif group > 0 and result:
                if not result.startswith("零"):
                    result = "零" + result
                    
            group += 1
        
        if result.startswith("一十"):
            result = result[1:]
        
        return result
    
    def _convert_section(self, n: int) -> str:
        """将 1~9999 的数字转为中文"""
        if n == 0:
            return "零"
            
        result = ""
        str_n = str(n)
        length = len(str_n)
        
        for i, digit in enumerate(str_n):
            d = int(digit)
            unit = self.units[length - i - 1]
            if d != 0:
                result += self.digits[d] + unit
            else:
                if result and result[-1] != "零":
                    result += "零"
        
        return result.rstrip("零")


class TextToImageAPI:
    """文字转图片API"""
    
    def __init__(self, 
                 font_path: Optional[str] = None,
                 font_size: int = 36,
                 text_color: str = "#2E86AB",
                 background_color: str = "#F8F9FA",
                 padding: int = 20,
                 line_spacing: int = 10,
                 max_width: int = 800,
                 max_height: int = 2000,
                 max_text_length: int = 2000):
        self.font_size = font_size
        self.text_color = self._parse_color(text_color)
        self.background_color = self._parse_color(background_color)
        self.padding = padding
        self.line_spacing = line_spacing
        self.max_width = max_width
        self.max_height = max_height
        self.max_text_length = max_text_length
        
        self.font = self._load_font(font_path, font_size)
        self._font_metrics_cache = {}
    
    def _parse_color(self, color_str: str) -> Tuple[int, int, int]:
        """解析颜色字符串"""
        if color_str.startswith('#'):
            color_str = color_str.lstrip('#')
            if len(color_str) == 3:
                color_str = ''.join([c*2 for c in color_str])
            return tuple(int(color_str[i:i+2], 16) for i in (0, 2, 4))
        elif color_str.startswith('rgb'):
            match = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color_str)
            if match:
                return tuple(int(x) for x in match.groups())
        return (0, 0, 0)
    
    def _load_font(self, font_path: Optional[str], font_size: int) -> ImageFont.FreeTypeFont:
        """加载字体"""
        try:
            system_fonts = [
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
            ]
            
            if font_path and os.path.exists(font_path):
                return ImageFont.truetype(font_path, font_size)
            
            for font in system_fonts:
                if os.path.exists(font):
                    return ImageFont.truetype(font, font_size)
            
            return ImageFont.load_default()
            
        except Exception as e:
            print(f"字体加载失败，使用默认字体: {e}")
            return ImageFont.load_default()
    
    def _get_text_bbox(self, text: str) -> Tuple[int, int, int, int]:
        """获取文本边界框，带缓存"""
        if text in self._font_metrics_cache:
            return self._font_metrics_cache[text]
        
        bbox = self.font.getbbox(text)
        self._font_metrics_cache[text] = bbox
        return bbox
    
    def _wrap_text_smart(self, text: str, max_width: int) -> List[str]:
        """智能文本换行处理"""
        if not self.font:
            return [text]
        
        lines = []
        current_line = ""
        words = []
        
        for char in text:
            if char.isspace():
                if words:
                    current_line = ''.join(words)
                    words = []
                current_line += char
            elif ord(char) < 128:
                words.append(char)
            else:
                if words:
                    current_line = ''.join(words)
                    words = []
                test_line = current_line + char
                bbox = self._get_text_bbox(test_line)
                test_width = bbox[2] - bbox[0]
                
                if test_width <= max_width - 2 * self.padding:
                    current_line = test_line
                else:
                    if current_line.strip():
                        lines.append(current_line.strip())
                    current_line = char
        
        if words:
            current_line = current_line + ''.join(words)
        
        if current_line.strip():
            lines.append(current_line.strip())
        
        return lines
    
    def convert_to_image(self, 
                        text: str, 
                        output_path: Optional[str] = None,
                        format: str = 'PNG') -> Image.Image:
        """
        将文本转换为图片
        
        Args:
            text: 要转换的文本
            output_path: 输出路径
            format: 图片格式
        
        Returns:
            PIL Image对象
        """
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        
        if len(text) > self.max_text_length:
            text = text[:self.max_text_length] + "...(文本过长，已截断)"
        
        # 计算图片尺寸
        max_text_width = self.max_width - 2 * self.padding
        lines = self._wrap_text_smart(text, self.max_width)
        
        max_width = 0
        total_height = 0
        
        for line in lines:
            bbox = self._get_text_bbox(line)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            
            max_width = max(max_width, line_width)
            total_height += line_height + self.line_spacing
        
        if lines:
            total_height -= self.line_spacing
        
        width = min(max_width + 2 * self.padding, self.max_width)
        height = min(total_height + 2 * self.padding, self.max_height)
        
        # 创建图片
        image = Image.new('RGB', (width, height), self.background_color)
        draw = ImageDraw.Draw(image)
        
        y_position = self.padding
        
        for line in lines:
            if not line.strip():
                y_position += self.font_size + self.line_spacing
                continue
                
            bbox = self._get_text_bbox(line)
            line_height = bbox[3] - bbox[1]
            text_width = bbox[2] - bbox[0]
            
            x_position = (width - text_width) // 2
            
            draw.text((x_position, y_position), line, font=self.font, fill=self.text_color)
            
            y_position += line_height + self.line_spacing
        
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            image.save(output_path, format=format, optimize=True)
        
        return image
    
    def convert_for_bot(self, 
                       text: str, 
                       save_dir: str = "plugins/rqhmain/picall") -> str:
        """
        专为机器人设计的转换方法
        
        Args:
            text: 要转换的文本
            save_dir: 保存目录
        
        Returns:
            图片文件路径
        """
        timestamp = int(time.time())
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
        filename = f"text_image_{timestamp}_{text_hash}.png"
        output_path = os.path.join(save_dir, filename)
        
        self.convert_to_image(text, output_path)
        
        return output_path


class IPInfoAPI:
    """IP信息查询API"""
    
    def __init__(self, base_url: str = "https://api.52vmy.cn/api/query/itad/pro"):
        self.base_url = base_url
    
    def query_ip(self, ip_address: str) -> str:
        """
        查询IP信息
        
        Args:
            ip_address: IP地址
        
        Returns:
            IP信息的JSON字符串
        """
        try:
            url = f"{self.base_url}?ip={urllib.parse.quote(ip_address)}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"
