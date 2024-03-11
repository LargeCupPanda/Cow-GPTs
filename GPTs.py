import plugins
import json
import re
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
import os
import time
import random

from .GPTsChatBot import GPTsChatBot


@plugins.register(
    name="GPTs",
    desc="支持调用GPTs",
    version="1.0",
    author="PandaAI",
    desire_priority=66
)
class GPTs(Plugin):
    def __init__(self):
        super().__init__()
        self.session_data = {}
        self.c_modelpro = GPTsChatBot()
        self.all_keywords = []
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
                logger.info(f"[GPTs] 加载配置文件成功: {self.config}")
                logger.info(f"--------------------------Config content: {self.config['models']}")
                if not isinstance(self.config, dict):
                    logger.error("self.config is not a dictionary.")
                else:
                    self.models = self.config.get('models', {})
                    logger.debug(f"--------------------------self.models: {self.models}")
                logger.info("[GPTs] inited")
        except Exception as e:
            logger.error(f"[GPTs] init error: {e}")

    def on_handle_context(self, e_context: EventContext):
        context = e_context['context']
        logger.debug(f"GPTs获取到用户输入：{context.content}")
        msg: ChatMessage = context['msg']
        isgroup = e_context["context"].get("isgroup")
        user_id = msg.actual_user_id if isgroup else msg.from_user_id

        # 过滤不需要处理的内容类型
        if context.type not in [ContextType.TEXT, ContextType.IMAGE]:
            return

        if context.type == ContextType.TEXT:
            # 获取当前会话状态
            session_state, session_data = self.get_session_state(user_id)
    
            if session_state == "NORMAL":
                self.handle_normal_context(e_context)
            else:
                # 尝试查找对应的处理方法
                handler_method_name = f"handle_{session_state}_request"
                if hasattr(self, handler_method_name):
                    handler_method = getattr(self, handler_method_name)
                    handler_method(e_context, session_data)
                else:
                    # 回退到通用处理方法
                    self.handle_generic_request(e_context, session_state, session_data)
        else:
            # 图片或其他功能扩展
             return  

    def handle_normal_context(self, e_context: EventContext):
        context = e_context['context']
        msg: ChatMessage = context['msg']
        isgroup = e_context["context"].get("isgroup")
        user_id = msg.actual_user_id if isgroup else msg.from_user_id
        nickname = msg.actual_user_nickname  # 获取nickname
        start_time = time.time()  # 开始计时

        # 遍历配置文件中定义的模型，根据关键字判断是否触发某个角色
        for model_name, model_info in self.models.items():
            for keyword in model_info['keywords']:
                if keyword in context.content:
                    # 启动相应的会话状态
                    self.start_session(user_id, model_name)
                    # 处理自定义请求
                    self.handle_custom_request(e_context, model_name, user_id)
                    return

        if "重置会话" in context.content:
            self.c_modelpro.clear_all_histories()
            _set_reply_text("记录清除，会话已重置。", e_context, level=ReplyType.TEXT)
            return
        elif "清除我的会话" in context.content:
            # 调用 clear_user_history 方法并检查操作是否成功
            if self.c_modelpro.clear_user_history(user_id):
                _set_reply_text("您的会话历史已被清除。", e_context, level=ReplyType.TEXT)
            return
        elif context.content == "帮助" or context.content == "功能":

            for model_name, model_info in self.models.items():
                keywords = model_info.get('keywords', [])
                self.all_keywords.extend(keywords)

            # 完整的功能指南
            features_guide = (
                "🌈 GPTs使用指南 🌈\n\n"
                f"🎨 魔法口令：{self.all_keywords} 🌟[退出]口令切换模型\n"
                "🔄 '重置会话' - 清除当前会话历史\n"
                "💬 其他普通文本 - 聊天机器人智能回复\n"
                "\n🌟 有任何问题或建议，随时欢迎反馈！"
            )

            _set_reply_text(features_guide, e_context, level=ReplyType.TEXT)
            return

        # 调用模型库的模型进行处理
        else:
            user_input = context.content
            response = self.c_modelpro.get_model_reply(user_input, user_id)

            response = format_response(response)
            logger.debug(f"model_response: {response}")
            paragraphs = re.split(r'。|？|\n\n+', response)

            # paragraphs = response.split('\n\n')
            # paragraphs = split_paragraphs(model_response)
            for i, paragraph in enumerate(paragraphs):
                if paragraph.strip():  # 确保段落不只是空白
                    logger.debug(f"-------------默认--第{i}次段落分割-----------: {paragraph}")
                    _send_info_wechat(e_context, paragraph)
                    time.sleep(random.uniform(4, 10))

            # 所有段落处理完毕后，设置BREAK_PASS
            e_context.action = EventAction.BREAK_PASS
            return

    def handle_generic_request(self, e_context: EventContext, session_state: str, session_data):
        model_info = self.models.get(session_state)
        if model_info:
            model_id = model_info['model_id']

            model_names = model_info['keywords']

            logger.debug(f"激活{model_names}")
            context = e_context['context']
            msg: ChatMessage = context['msg']

            isgroup = e_context["context"].get("isgroup")
            user_id = msg.actual_user_id if isgroup else msg.from_user_id
            # nickname = msg.actual_user_nickname  # 获取nickname
            if "退出" in context.content:
                self.c_modelpro.clear_user_history(user_id)
                self.end_session(user_id)
                logger.debug(f"清除用户记录和会话状态")
                self.c_modelpro.set_gpts_model("gpt-4-gizmo-g-hG7vgO0nL", user_id)
                _set_reply_text(f"{model_names}已退出，已切换到默认模型：gpt-4-gizmo-g-hG7vgO0nL", e_context,
                                level=ReplyType.TEXT)
            else:
                self.c_modelpro.set_gpts_model(model_id, user_id)
                model_response = self.c_modelpro.get_model_reply(context.content, user_id)

                model_response = format_response(model_response)

                logger.debug(f"{model_id}: {model_response}")
                # 按段落分割响应
                paragraphs = model_response.split('。|？|\n\n+')

                # paragraphs = re.split(r'。|？|\n\n+', model_response)
                for i, paragraph in enumerate(paragraphs):
                    if paragraph.strip():  # 确保段落不只是空白
                        logger.debug(f"---------------第{i}次段落分割-----------: {paragraph}")
                        _send_info_wechat(e_context, paragraph)
                        time.sleep(random.uniform(3, 7))

                # 所有段落处理完毕后，设置BREAK_PASS
                e_context.action = EventAction.BREAK_PASS

            return

    def handle_custom_request(self, e_context: EventContext, model_name: str, user_id: str):

        model_id = self.models[model_name]['model_id']

        logger.debug(f"激活{model_id}")
        context = e_context['context']
        msg: ChatMessage = context['msg']

        isgroup = e_context["context"].get("isgroup")
        user_id = msg.actual_user_id if isgroup else msg.from_user_id
        # nickname = msg.actual_user_nickname  # 获取nickname
        if "退出" in context.content:
            self.c_modelpro.clear_user_history(user_id)
            self.end_session(user_id)
            logger.debug(f"清除用户记录和会话状态")
            self.c_modelpro.set_gpts_model("gpt-4-gizmo-g-hG7vgO0nL", user_id)
            _set_reply_text(f"{model_id}退出，已切换到默认模型：gpt-4-gizmo-g-hG7vgO0nL", e_context,
                            level=ReplyType.TEXT)
        else:
            self.c_modelpro.set_gpts_model(model_id, user_id)
            model_response = self.c_modelpro.get_model_reply(context.content, user_id)
            logger.debug(f"{model_id}: {model_response}")
            # 按段落分割响应
            paragraphs = model_response.split('\n\n')

            # paragraphs = re.split(r'。|？|\n\n+', model_response)
            for i, paragraph in enumerate(paragraphs):
                if paragraph.strip():  # 确保段落不只是空白
                    logger.debug(f"---------------第{i}次段落分割-----------: {paragraph}")
                    _send_info_wechat(e_context, paragraph)
                    time.sleep(random.uniform(3, 7))

            # 所有段落处理完毕后，设置BREAK_PASS
            e_context.action = EventAction.BREAK_PASS

        return

    def base_url(self):
        return self.cc_api_base

    def start_session(self, user_id, state, data=None):
        self.session_data[user_id] = (state, data)
        logger.debug(f"用户{user_id}开始会话，状态: {state}, 数据: {data}")

    def end_session(self, user_id):
        self.session_data.pop(user_id, None)
        logger.debug(f"用户{user_id}结束会话")

    def get_session_state(self, user_id):
        logger.debug(f"获取用户{user_id}的会话状态: {self.session_data.get(user_id)}")
        return self.session_data.get(user_id, ("NORMAL", None))

    def get_help_text(self, verbose=False, **kwargs):
        # 初始化帮助文本，插件的基础描述
        help_text = "\n🤖 WeChat基于代理的GPTs\n"

        for model_name, model_info in self.models.items():
            keywords = model_info.get('keywords', [])
            self.all_keywords.extend(keywords)

        # 如果不需要详细说明，则直接返回帮助文本
        if not verbose:
            return help_text

        # 添加详细的使用方法到帮助文本中
        help_text += f"""
                    🌈 插件功能指南 🌈
                          🎨 魔法口令：{self.all_keywords}
                          💬 智能聊天：聊天机器人将智能回复您的消息。
                          🔄 '重置会话'：清除当前会话历史，开始新的对话。
                """
        # 返回帮助文本
        return help_text

def _send_info_wechat(e_context: EventContext, content: str):
    reply = Reply(ReplyType.TEXT, content)
    channel = e_context["channel"]
    channel.send(reply, e_context["context"])


def _set_reply_text(content: str, e_context: EventContext, level: ReplyType = ReplyType.ERROR):
    reply = Reply(level, content)
    e_context["reply"] = reply
    e_context.action = EventAction.BREAK_PASS

def format_response(response):
    # 检查是否以指定的字符序列开头
    if response.startswith("``````"):
        # 去除开头的字符序列
        response = response[6:]  # 从第七个字符开始截取，因为“``````”占了六个字符
    # 去除可能的前后空格或换行符
    response = response.strip()
    return response

def split_paragraphs(text):
    # 在文本末尾添加一个虚拟的分割符，以便捕获最后一个段落
    text += '\n'

    regex_pattern = re.compile(r'(。|？|\n\n+)')
    split_points = [(m.start(), m.group()) for m in regex_pattern.finditer(text)]

    # 初始化段落列表
    paragraphs = []

    # 遍历所有可能的分割点
    start = 0
    for point, match in split_points:
        # 添加当前段落到列表，包括分割符
        paragraphs.append(text[start:point + len(match)])
        # 更新段落开始位置为当前分割点之后
        start = point + len(match)

    # 返回处理后的段落列表
    return paragraphs