"""
WorkplaceThinker 隐私保护模块

提供自动 PII（Personally Identifiable Information）脱敏功能：
1. 手机号码脱敏
2. 邮箱脱敏
3. 身份证号码脱敏
4. 可选的特定敏感人名或公司名脱敏（暂存）
"""

import re
from typing import Dict, List, Set

class PrivacyEngine:
    """隐私保护引擎"""
    
    def __init__(self):
        # 预编译正则以提升性能
        # 匹配中国大陆手机号
        self.phone_regex = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
        # 匹配邮箱
        self.email_regex = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
        # 匹配中国大陆身份证号（18位）
        self.idcard_regex = re.compile(r"(?<!\d)([1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|10|11|12)(?:0[1-9]|[1-2]\d|30|31)\d{3}[\dXXx])(?!\d)")
        
        self.custom_redact_words: Set[str] = set()

    def add_custom_redact_word(self, word: str):
        """添加自定义屏蔽词，如具体的公司名"""
        if word and len(word) > 1:
            self.custom_redact_words.add(word)

    def redact_text(self, text: str) -> str:
        """对文本进行 PII 脱敏"""
        if not text:
            return text
            
        redacted = text
        
        # 脱敏手机号 (13812345678 -> 138****5678)
        redacted = self.phone_regex.sub(lambda m: f"{m.group(1)[:3]}****{m.group(1)[7:]}", redacted)
        
        # 脱敏邮箱 (abc@example.com -> a***c@example.com)
        def mask_email(m):
            email = m.group(1)
            parts = email.split('@')
            if len(parts[0]) > 2:
                name = parts[0][0] + "***" + parts[0][-1]
            else:
                name = "***"
            return f"{name}@{parts[1]}"
        redacted = self.email_regex.sub(mask_email, redacted)
        
        # 脱敏身份证号 (前6位和后4位保留，中间屏蔽)
        redacted = self.idcard_regex.sub(lambda m: f"{m.group(1)[:6]}********{m.group(1)[-4:]}", redacted)
        
        # 脱敏自定义词汇
        for word in self.custom_redact_words:
            if word in redacted:
                # 简单替换为 ***
                redacted = redacted.replace(word, "*" * len(word))
                
        return redacted

    def redact_dict(self, data: Dict) -> Dict:
        """递归地对字典中的字符串值进行脱敏"""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = self.redact_text(v)
            elif isinstance(v, dict):
                result[k] = self.redact_dict(v)
            elif isinstance(v, list):
                result[k] = [self.redact_text(item) if isinstance(item, str) else 
                            (self.redact_dict(item) if isinstance(item, dict) else item) 
                            for item in v]
            else:
                result[k] = v
        return result
