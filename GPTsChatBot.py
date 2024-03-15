import openai
import os
import json
import re
from common.log import logger


class GPTsChatBot:
    def __init__(self):
        # 初始化 user_models 属性
        self.user_models = {}  # 假设这是一个字典，根据你的具体需求进行调整

        # 从配置文件中加载模型配置
        curdir = os.path.dirname(__file__)
        self.config_path = os.path.join(curdir, "config.json")
        logger.debug(f"尝试读取配置文件: {self.config_path}")
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            logger.debug(f"配置文件内容: {config}")

            # 确保先定义self.models
            self.models = config.get("models", {})

            # OpenAI配置
            self.openai_api_key = config.get("open_ai_api_base", "")
            self.openai_api_base = config.get("open_ai_api_base", "https://api.aigcbest.top/v1")
            self.openai_model = self.models["默认"]['model_id']
            # 其他配置
            self.user_histories = {}
            # 设置默认用户 ID
            self.user_histories[self.DEFAULT_USER_ID] = []
            self.ai_model = config.get("ai_model", "OpenAI")
            self.max_history_length = config.get("max_history_length", 5)
        except Exception as e:
            logger.error(f"[GPTsChatBot] init error: {e}")

    # 常量定义
    DEFAULT_USER_ID = "default_user"

    # GPTs 选择
    def set_gpts_model(self, model_id, user_id=None):
        # 通过模型ID查找模型名称
        context_name = next((name for name, info in self.models.items() if info['model_id'] == model_id), None)
        if not context_name:
            logger.error(f"未找到模型ID对应的模型：{model_id}")
            return "模型设置失败"

        # 设置模型
        self.openai_model = model_id
        logger.debug(f"已全局切换到 {context_name} GPTs: {model_id}。")
        return f"已全局切换到 {context_name} GPTs: {model_id}。"

    def get_user_history(self, user_id=None):
        user_id = user_id or self.DEFAULT_USER_ID
        if user_id not in self.user_histories:
            self.user_histories[user_id] = []
        logger.debug(f"当前用户 {user_id} 的历史记录: {self.user_histories[user_id]}")
        return self.user_histories[user_id]

    def clear_user_history(self, user_id=None):
        user_id = user_id or self.DEFAULT_USER_ID
        if user_id in self.user_histories:
            self.user_histories[user_id] = []
            logger.debug(f"已清空用户 {user_id} 的历史记录。")
            return True
        return False

    def clear_all_histories(self):
        self.user_histories.clear()
        logger.debug("已清空所有历史记录。")


    def add_message_openai(self, role, content, user_id=None):
        user_id = user_id or self.DEFAULT_USER_ID
        history = self.get_user_history(user_id)
        history.append({"role": role, "content": content})
        self._trim_history(history)

    def _trim_history(self, history):
        max_history_length = self.max_history_length  # 示例值

        if not history:
            return
        # 移除第一条 'assistant' 记录（如果存在）
        if history[0]["role"] == "assistant":
            history.pop(0)
            logger.debug("移除1条助手记录")

        # 如果模型不是 OpenAI 或 Qwen 且第一条是 'system'，则移除
        if self.ai_model not in ["OpenAI"] and history[0]["role"] == "system":
            history.pop(0)
            logger.debug("移除1条系统提示")

        # 根据模型特定逻辑修剪历史记录
        if self.ai_model in ["OpenAI"] and history and history[0]["role"] == "system":
            while len(history) > max_history_length:
                # 确保至少有3条历史记录
                if len(history) > 3:
                    logger.debug("移除2条历史记录")
                    history[:] = history[:1] + history[3:]
                else:
                    break
        else:
            while len(history) > max_history_length - 1:
                if len(history) > 2:
                    logger.debug("移除2条历史记录")
                    history[:] = history[2:]
                else:
                    break

    def get_model_reply(self, user_input, user_id=None):
        user_id = user_id or self.DEFAULT_USER_ID
        # 从用户模型映射中获取当前用户的模型，如果没有则使用默认模型
        current_model = self.user_models.get(user_id, self.openai_model)
        logger.debug(f"当前使用的模型为：{current_model}")
        logger.debug(f"当前使用的self.ai_model模型为：{self.ai_model}")
        logger.debug("调用 _get_reply_openai")  # 调试打印
        return self._get_reply_openai(user_input, user_id, model=current_model)

    # 获取OpenAI 模型的响应
    def _get_reply_openai(self, user_input, user_id=None, model=None):
        logger.debug(f"进入 _get_reply_openai 方法")
        if not user_input.strip():
            return "用户输入为空"
        user_id = user_id or self.DEFAULT_USER_ID
        # 使用针对当前用户设置的模型，如果没有则使用传递进来的模型参数
        self.model = model or self.user_models.get(user_id, self.openai_model)
        logger.debug(f"当前用户 ID: {user_id}")
        logger.debug(f"向 OpenAI 发送消息: {user_input} 使用模型: {self.model}")
        self.add_message_openai("user", user_input, user_id)
        try:
            history = self.get_user_history(user_id)
            logger.debug(f"传递给 OpenAI 的历史记录: {history}")  # 调试打印
            response = openai.ChatCompletion.create(
                model=self.model,  # 使用设置的模型变量
                messages=history
            )
            reply_text = response["choices"][0]["message"]['content']
            self.add_message_openai("assistant", reply_text, user_id)

            ## 新增部分
            reply_text = re.sub(r'json \n.*?\n', '', reply_text, flags=re.DOTALL)

            logger.debug(f"---------------GPTsChatBot未拆分-----------: {reply_text}")

            return f"{reply_text}"

        except Exception as e:
            # 发生异常时，移除最后一条用户输入
            print(f"发生异常: {e}")
            history = self.get_user_history(user_id)
            history.pop(-1) if history and history[-1]["role"] == "user" else None
            return self.handle_exception(e)

    def handle_exception(self, e):
        message = "哎呀，遇到了点小波折，让我们稍后再来一次。"
        if isinstance(e, openai.error.RateLimitError):
            # logger.warn("[OPENAI] RateLimitError: {}".format(e))
            message = f"我们太火热了，得冷静一下。稍等片刻再试试？"
        elif isinstance(e, openai.error.Timeout):
            # logger.warn("[OPENAI] Timeout: {}".format(e))
            message = f"这里似乎有条时间的河，我们不小心迷路了。稍后再试？"
        elif isinstance(e, openai.error.APIError):
            # logger.warn("[OPENAI] APIError: {}".format(e))
            message = f"API 好像在捉迷藏，找不到它了。稍后再试试？"
        elif isinstance(e, openai.error.APIConnectionError):
            # logger.warn("[OPENAI] APIConnectionError: {}".format(e))
            message = f"网络小巷子里似乎有堵墙，穿不过去呢。稍后再试？"
        else:
            message = (f"网络出现了未知的小惊喜····")

        return message
