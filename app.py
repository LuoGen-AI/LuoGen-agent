import os
import gradio as gr
import configparser
from fastapi import FastAPI, Request, Response
import logging
import sys
import time
import shutil
import uuid
import gc
import torch
import cv2

# 移除直接导入human_base核心模块，改为使用generate_video.py中的domake方法
from utils.video_processor import (
    download_and_extract_text,
)
from utils.key_manager import (
    save_api_key,
    delete_api_key,
    refresh_api_key,
)
from utils.voice_processor import (
    run_GPTvoice_command,
    handle_audio_creation,
    get_pt_files,
    download_audio,
    get_bgm_list,
    get_background_images,
    add_bgm_to_video_function,
    add_bgm_to_video_function_with_random_choice,
    save_subtitle_text,
    generate_subtitle_only,
    generate_audio_only
)
from utils.update_handler import (
    update_platform_elements,
    do_update,
)
from utils.service_launcher import (
    start_digit_human,
    start_cosyvoice,
)

from utils.video_cover_image import (
    generate_cover_image_gui,
)
from ai_processing.text_rewriter import (
    AI_write_descriptions,
    execute_rewrite,
)
from video_tools.generate_video import get_trained_models, generate_tuilionnx_video, get_face_list, refresh_face_list

from video_tools.subtitle_utils import (
    add_subtitles_to_video_with_style,
    FONT_FAMILIES,
)
from video_tools.publisher import (
    auto_publishing_videos_DY,
    auto_publishing_videos_XHS,
    auto_publishing_videos_SPH,
    auto_publishing_videos_ALL,
    auto_publishing_videos_DY_ALL,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

#设置human_base的初始变量
if_gfpgan_default = True
if_res_default = False
if_ifface_default = True


# 设置标准输出无缓冲
sys.stdout.reconfigure(line_buffering=True)


def refresh_voice_list():
    """获取并返回最新的音色列表

    Returns:
        gr.update: 更新下拉列表的选项
    """
    pt_files = get_pt_files()  # 获取最新的音色文件列表
    choices = [name for name, _ in pt_files]  # 返回音色名称列表
    return gr.update(choices=choices)


def refresh_bgm_list():
    bgm_list = get_bgm_list()
    choices = [name for name, _ in bgm_list]
    return gr.update(choices=choices)


def refresh_background_images():
    images = get_background_images()
    choices = [name for name, _ in images]
    return gr.update(choices=choices)


def cancel_update():
    """取消更新操作

    Returns:
        tuple: 状态信息和对话框可见性更新
    """
    return ("用户取消更新", gr.update(visible=False))


def create_ui():
    """创建UI界面并绑定各种事件处理函数

    Returns:
        gr.Blocks: 创建好的Gradio Blocks界面
    """
    # 禁用Gradio分析功能
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

    with gr.Blocks(title="罗根 一键追爆智能体", analytics_enabled=False) as demo:
        app = demo.app

        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 允许所有源
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 单独处理 WebSocket 的 OPTIONS 请求
        @app.middleware("http")
        async def websocket_cors_middleware(request, call_next):
            if request.url.path == "/queue/join":
                if request.method == "OPTIONS":
                    response = Response()
                    response.headers["Access-Control-Allow-Origin"] = "*"
                    response.headers["Access-Control-Allow-Methods"] = (
                        "GET, POST, OPTIONS"
                    )
                    response.headers["Access-Control-Allow-Headers"] = "*"
                    return response
            return await call_next(request)

        with gr.Group(visible=False) as main_interface:  # 将整个界面包装在不可见组中
            with gr.Row():
                with gr.Column():
                    with gr.Row():
                        gr.Markdown(
                            """
                            AI
                            """
                        )

            with gr.Row():
                with gr.Row():
                    with gr.Column():
                        link_input = gr.Textbox(
                            label="请输入视频链接地址",
                            elem_classes="custom-textbox1",
                            lines=4,
                        )
                        with gr.Row():
                            Post_on_DY_ALL = gr.Button(
                                "一键追爆款并发布到各平台", elem_classes="blue-button"
                            )
                        # # 添加图像显示组件
                        # )
                    with gr.Column():
                        extract_text_button = gr.Button("提取视频文案")
                        text_input = gr.Textbox(
                            label="可手动修改文案",
                            elem_classes="custom-textbox",
                            value="",
                        )
                        with gr.Row():
                            with gr.Column():
                                with gr.Row():
                                    api_key_input = gr.Textbox(
                                        label="输入Deepseek API Key",
                                        elem_classes=["compact-textbox"],
                                        value="",
                                    )
                                    save_api_key_button = gr.Button("保存API Key")
                                    delete_api_key_button = gr.Button("删除API Key")

                                    # 读取配置,选择API Key
                                    config = configparser.ConfigParser()
                                    config.read("config.ini", encoding="utf-8")
                                    keys = config.get("deepseek_apikey", "key").split(
                                        ","
                                    )
                                    default_key = keys[0] if keys else None
                                    # 添加key选择下拉框
                                    api_key = gr.Dropdown(
                                        choices=keys,
                                        value=None,
                                        label="必须先选择一个key",
                                    )
                                    refresh_api_key_button = gr.Button(
                                        "刷新keys",
                                        elem_classes=["custom-btn"],
                                        variant="primary",
                                        visible=False,
                                    )
                                with gr.Row():
                                    ai_mode = gr.Radio(
                                        elem_classes=["compact-radio"],
                                        choices=["AI自动仿写", "根据指令仿写"],
                                        label="仿写模式选择（以下两种方式均调用deepseek671b满血版）",
                                        value="AI自动仿写",
                                    )
                                    AI_prompt = gr.Textbox(
                                        label="prompt，即改写文案的规则和要求，例：请用幽默的口吻改写这段文案",
                                        elem_classes=[
                                            "custom-textbox",
                                            "compact-textbox",
                                        ],
                                        lines=1,
                                        visible=False,
                                    )
                                    # 修改为单个按钮
                                    AI_execute_button = gr.Button(
                                        "执行仿写",
                                        elem_classes=["custom-btn"],
                                        variant="primary",
                                    )
            with gr.Row():
                # 状态显示区域（统一的状态显示）
                status_output = gr.Textbox(label="状态信息")

            with gr.Row():
                with gr.Column():
                    with gr.Row():
                        video_model_dropdown = gr.Dropdown(
                            choices=get_trained_models(),
                            label="选择人物形象",
                            value=(
                                get_trained_models()[0]
                                if get_trained_models()
                                else None
                            ),
                        )
                        # 移除背景图片相关组件
                        # )
                        #     ),
                        # )
                        # )
                        # )
                        
                        # 创建隐藏的背景相关组件以保持兼容性
                        background_image = gr.Image(
                            label="背景图片功能已移除", type="filepath", visible=False
                        )
                        background_image_list = gr.Dropdown(
                            choices=[], label="背景图片功能已移除", visible=False
                        )
                        check_box = gr.Checkbox(
                            label="背景替换功能已移除", value=False, interactive=False, visible=False
                        )
                    with gr.Row():
                        video_output = gr.Video(label=" 视频预览 ", interactive=False)
                        Create_Digital_Human = gr.Button("生成视频")
                    with gr.Row():
                        srt_text_output = gr.Textbox(
                            lines=10,
                            label="字幕文本内容",
                            elem_classes=["custom-textbox"],
                        )
                        save_subtitle_button = gr.Button("保存字幕文本")

                with gr.Column():
                    with gr.Row():
                        pt_files = get_pt_files()
                        pt_file_dropdown = gr.Dropdown(
                            label="选择音色",
                            choices=[name for name, _ in pt_files],  # 显示名称列表
                            value=(
                                pt_files[0][0] if pt_files else None
                            ),  # 默认选择第一个音色的显示名称
                            type="index",  # 使用索引来选择
                        )
                        # 在适当的位置添加刷新按钮
                        refresh_button = gr.Button("刷新音色")

                        # 绑定按钮点击事件
                        refresh_button.click(
                            fn=refresh_voice_list,  # 使用具名函数替代lambda
                            outputs=[
                                pt_file_dropdown
                            ],  # 假设 pt_file_dropdown 是音色选择的下拉框
                        )
                    with gr.Row():
                        start_GPTvoice_button = gr.Button("启动语音接口")
                        voice_status = gr.Markdown(
                            "🔴 未启动", elem_classes="status-label"
                        )
                    speed = gr.Number(
                        value=1,
                        label="语速调节",
                        minimum=0.5,
                        maximum=2.0,
                        step=0.1,
                    )
                    Create_audio = gr.Button(" 生成音频")
                    audio_output = gr.Audio(
                        label="音频预览",
                        type="filepath",
                        interactive=True,
                        elem_id="audio_output",
                    )
                    download_button = gr.DownloadButton("下载音频")
                    Create_subtitle = gr.Button("单独生成字幕")


            # 字幕设置和视频描述区域
            with gr.Row():
                # 字幕设置
                with gr.Column(scale=2):
                    with gr.Row():
                        font_family = gr.Dropdown(
                            choices=FONT_FAMILIES,  # 使用字体真实名称列表
                            value=(
                                FONT_FAMILIES[0] if FONT_FAMILIES else "Microsoft YaHei"
                            ),
                            label="字体",
                        )
                        font_size = gr.Number(value=11, label="字体大小")
                    with gr.Row():
                        font_color = gr.ColorPicker(value="#FFFFFF", label="字体颜色")
                        outline_color = gr.ColorPicker(
                            value="#000000", label="描边颜色"
                        )
                    bottom_margin = gr.Number(value=60, label="底部边距")

                # 操作按钮和描述输入
                with gr.Column(scale=1):
                    add_subtitle_btn = gr.Button("添加字幕到视频", variant="primary")
                    AI_miaoshu = gr.Button("deepseek撰写视频描述与话题标签")
                    # 视频描述和话题（移到AI撰写按钮下方）
                    two_line_input = gr.Textbox(
                        label="视频描述和话题标签",
                        placeholder="视频描述（换行）#话题#话题",
                        lines=2,
                        interactive=True,
                    )
                with gr.Column(scale=1):
                    use_random_choice = gr.Button("随机选择背景音乐")
                    skip_bgm_add_box = gr.Checkbox(
                        label="全自动时是否跳过添加随机BGM",
                        value=False,
                        interactive=True,
                    )
                    bgm_list = gr.Dropdown(
                        choices=[name for name, _ in get_bgm_list()],
                        value=None,  # 默认选择第一个音色的显示名称
                        label="背景音乐",
                        interactive=True,
                    )
                    user_upload_bgm = gr.File(type="filepath")
                    refresh_bgm_button = gr.Button("刷新背景音乐")
                    bgm_volume_control = gr.Slider(
                        value=0.5,
                        label="背景音乐音量",
                        minimum=0,
                        maximum=1,
                        step=0.1,
                    )
                    refresh_bgm_button.click(
                        fn=refresh_bgm_list,
                        outputs=[bgm_list],
                    )
                    use_random_choice.click(
                        fn=add_bgm_to_video_function_with_random_choice,
                        inputs=[
                            video_output,
                            bgm_volume_control,
                        ],
                        outputs=[status_output, video_output],
                    )
                    add_bgm_to_video = gr.Button("添加背景音乐到视频")
                    add_bgm_to_video.click(
                        fn=add_bgm_to_video_function,
                        inputs=[
                            video_output,
                            bgm_list,
                            user_upload_bgm,
                            bgm_volume_control,
                        ],
                        outputs=[status_output, video_output],
                    )


            # 添加封面图
            with gr.Column(scale=2):
                with gr.Row():
                    when_auto_use_cover_checkbox = gr.Checkbox(
                        label="一键全流程时是否创建封面图", value=False
                    )
                    use_ai_checkbox = gr.Checkbox(
                        label="使用AI生成封面文案", value=False
                    )
                with gr.Row():
                    cover_text = gr.Textbox(
                        label="封面文案（非AI模式下必填）",
                        lines=2,
                        interactive=True,
                        placeholder="封面文案（非AI模式下必填）",
                    )
                    highlight_words_text = gr.Textbox(
                        label="高亮词（逗号分隔，非AI模式下必填）",
                        lines=2,
                        interactive=True,
                        placeholder="高亮词（逗号分隔，非AI模式下必填）",
                    )
                with gr.Row():
                    font_family_dropdown = gr.Dropdown(
                        choices=FONT_FAMILIES,
                        value=FONT_FAMILIES[0] if FONT_FAMILIES else "SimHei",
                        label="字体",
                        interactive=True,
                    )
                    font_size_number = gr.Number(
                        value=60, label="字体大小", interactive=True
                    )
                with gr.Row():
                    font_color_picker = gr.ColorPicker(
                        value="#FFFFFF", label="字体颜色", interactive=True
                    )
                    highlight_color_picker = gr.ColorPicker(
                        value="#FFD600", label="高亮颜色", interactive=True
                    )
                with gr.Row():
                    position_dropdown = gr.Dropdown(
                        choices=["top", "center", "bottom"],
                        value="bottom",
                        label="文字位置",
                        interactive=True,
                    )
                    frame_time_number = gr.Number(
                        value=None, label="抽帧时间点（秒，可选）", interactive=True
                    )
                with gr.Row():
                    generate_cover_btn = gr.Button(
                        "生成封面图", variant="primary", interactive=True
                    )
                with gr.Row():
                    cover_preview = gr.Image(label="封面预览", interactive=False)
                with gr.Row():
                    pulish_with_cover = gr.Checkbox(
                        label="发布时附带封面？", value=False
                    )
            # 发布按钮（页面最下方）
            with gr.Row():
                Post_on_DY = gr.Button("发布到dou音", size="large", variant="primary")
                Post_on_XHS = gr.Button("发布到小红薯", size="large", variant="primary")
                Post_on_SPH = gr.Button("发布到蝴蝶号", size="large", variant="primary")
            with gr.Row():
                Post_on_ALL = gr.Button(
                    "一键发布到各平台", size="large", variant="primary"
                )
                # 移除账号输入框（已移除登录系统）
                account = gr.Textbox(label="默认账号", value="", interactive=False, visible=False)
                pt_files_info = gr.Textbox(
                    label="音色信息，传递一个空值",
                    value="",
                    elem_classes="custom-textbox",
                )

            
            # 注释掉原有的human_base组件，保留以备后用
            # #迁移human_base中的组件到追爆后端主系统中
            
            # 新增tuilionnx数字人组件
            with gr.Column(scale=2):
                with gr.Column():
                    gr.Markdown("### TuiliONNX 数字人生成")
                    video = gr.Video(label="上传视频", interactive=False)
                    
                    with gr.Row():
                        batch_size = gr.Number(label="批次大小", value=4, minimum=1, maximum=16, interactive=True)
                        sync_offset = gr.Number(label="音画同步偏移", value=0, minimum=-10, maximum=10, interactive=True)
                    
                    with gr.Row():
                        scale_h = gr.Number(label="遮罩高度比例", value=1.6, minimum=0.5, maximum=3.0, step=0.1, interactive=True)
                        scale_w = gr.Number(label="遮罩宽度比例", value=3.6, minimum=0.5, maximum=5.0, step=0.1, interactive=True)
                        #增加是否进行压缩推理
                        compress_inference_check_box = gr.Checkbox(
                            label="是否进行压缩推理", value=False, interactive=True
                        )
                        # 增加是否美化牙齿
                        beautify_teeth_check_box = gr.Checkbox(
                            label="是否美化牙齿", value=False, interactive=True
                        )
                    tuilionnx_make_button = gr.Button("生成TuiliONNX数字人", variant="primary")

                with gr.Column():
                        face = gr.Dropdown(label="人物模型",choices=get_face_list(),interactive=True,value=None)
                        refresh_button = gr.Button("刷新视频模型列表")
                        refresh_button.click(fn=refresh_face_list, inputs=[face], outputs=[face])
                        output_time = gr.Textbox(label="生成时间",interactive=True)
                        output_url = gr.Textbox(label="分享视频下载URL",interactive=True)
                        one_list = gr.File(interactive=False,label="生成结果下载")
                        # 移除剪辑气口功能
                        # )
                        silence_check_box = gr.Checkbox(
                            label="剪辑气口功能已移除", value=False, interactive=False, visible=False
                        )
                        addAIWatermark_check_box = gr.Checkbox(
                            label="是否添加AI水印", value=True, interactive=True
                        )
                        digital_human_version_dropdown = gr.Dropdown(
                            choices=["旧版数字人", "新版数字人"],
                            value="新版数字人",
                            label="数字人版本选择",
                            interactive=True
                        )
                        subtitle_generation_type_dropdown = gr.Dropdown(
                            choices=["普通字幕生成", "高级字幕生成"],
                            value="高级字幕生成",
                            label="字幕生成类型",
                            interactive=True
                        )
            # 注释掉原有的make_button绑定，保留以备后用
            
            # 绑定新的TuiliONNX数字人生成按钮
            tuilionnx_make_button.click(
                generate_tuilionnx_video,
                inputs=[
                    face,
                    video,
                    audio_output, 
                    batch_size,
                    sync_offset,
                    scale_h,
                    scale_w,
                    compress_inference_check_box,
                    beautify_teeth_check_box,
                    silence_check_box,
                    addAIWatermark_check_box,
                    background_image,
                    background_image_list,
                    check_box
                ],
                outputs=[video_output, output_time, one_list, output_url]
            )

            # 调用API 为视频添加具有样式和特效的字幕
            with gr.Row():
                with gr.Column(scale=1):
                    upload_video_btn = gr.Button("利用返回的oss分享链接调用接口为视频添加字幕")
                    template_id = gr.Dropdown(
                            choices=[],  # 特效字幕功能已移除
                            value=None,
                            label="模板ID",
                        )
                    refresh_template_id_button = gr.Button("刷新视频模板列表")
                # 移除特效字幕相关UI组件
                #
                #
                #
                #     # 绑定按钮点击事件
                #                 template_id
                #             ],
                #         )
                #     )
                #     )
                #     )



            # 生成封面图按钮绑定的回调函数
            def handle_generate_cover(
                use_ai,
                api_key_value,
                cover_text_value,
                highlight_words_value,
                font_family_value,
                font_size_value,
                font_color_value,
                highlight_color_value,
                position_value,
                frame_time_value,
            ):
                # max_width, outline_size, outline_color 使用默认值
                image_path = generate_cover_image_gui(
                    use_ai=use_ai,
                    api_key=api_key_value,
                    text=cover_text_value,
                    highlight_words=highlight_words_value,
                    font_family=font_family_value,
                    font_size=int(font_size_value) if font_size_value else 60,
                    font_color=font_color_value,
                    highlight_color=highlight_color_value,
                    position=position_value,
                    frame_time=frame_time_value if frame_time_value else None,
                    # 默认参数
                    max_width=0.8,
                    outline_size=4,
                    outline_color="#000000",
                )
                return image_path

            generate_cover_btn.click(
                handle_generate_cover,
                inputs=[
                    use_ai_checkbox,
                    api_key,
                    cover_text,
                    highlight_words_text,
                    font_family_dropdown,
                    font_size_number,
                    font_color_picker,
                    highlight_color_picker,
                    position_dropdown,
                    frame_time_number,
                ],
                outputs=[cover_preview],
            )

            # 将提取文案的函数绑定到按钮点击事件，并指定输入输出
            extract_text_button.click(
                download_and_extract_text,
                inputs=[link_input],
                outputs=[text_input],
            )

            def toggle_controls(mode):
                return {
                    AI_prompt: gr.update(visible=(mode == "根据指令仿写")),
                    AI_execute_button: gr.update(visible=True),
                }

            ai_mode.change(
                fn=toggle_controls,
                inputs=[ai_mode],
                outputs=[AI_prompt, AI_execute_button],
            )

            AI_execute_button.click(
                execute_rewrite,
                inputs=[text_input, ai_mode, AI_prompt, api_key],
                outputs=[text_input],
            )

            # 启动语音接口服务
            start_GPTvoice_button.click(
                run_GPTvoice_command, inputs=[account], outputs=[voice_status]
            )

            # AI撰写描述
            AI_miaoshu.click(
                AI_write_descriptions,
                inputs=[text_input, api_key],  # 添加 model_dropdown 作为输入
                outputs=[two_line_input],
            )

            Create_audio.click(
                handle_audio_creation,
                inputs=[text_input, pt_file_dropdown, speed],
                outputs=[audio_output, status_output],
            )
            Create_subtitle.click(
                generate_subtitle_only,
                inputs=[audio_output, text_input, api_key],
                outputs=[srt_text_output, status_output],
            )
            save_subtitle_button.click(
                save_subtitle_text,
                inputs=[srt_text_output],
                outputs=[status_output],
            )
            download_button.click(
                download_audio,
                inputs=[audio_output],
                outputs=[download_button],
            )

            # 生成视频
            #     generate_digit_human,
            #         audio_output,
            #         video_model_dropdown,
            #         background_image,
            #         background_image_list,
            #         check_box,
            #         silence_check_box,
            #         addAIWatermark_check_box
            #     ],  # 添加模型选择下拉框
            # )

            # 一键发布到抖音
            Post_on_DY_ALL.click(
                auto_publishing_videos_DY_ALL,
                inputs=[
                    link_input,
                    two_line_input,
                    pt_file_dropdown,
                    video_model_dropdown,
                    api_key,
                    speed,
                    pt_files_info,
                    background_image,
                    background_image_list,
                    check_box,
                    skip_bgm_add_box,
                    bgm_list,
                    user_upload_bgm,
                    bgm_volume_control,
                    when_auto_use_cover_checkbox,
                    use_ai_checkbox,
                    cover_text,
                    highlight_words_text,
                    font_family_dropdown,
                    font_size_number,
                    font_color_picker,
                    highlight_color_picker,
                    position_dropdown,
                    frame_time_number,
                    pulish_with_cover,
                    silence_check_box,
                    digital_human_version_dropdown,
                    subtitle_generation_type_dropdown,
                    template_id
                ],  # 添加新增的组件
                outputs=[status_output],
            )

            # 绑定字幕添加按钮事件
            add_subtitle_btn.click(
                fn=add_subtitles_to_video_with_style,
                inputs=[
                    video_output,  # 视频路径
                    font_family,  # 字体
                    font_size,  # 字体大小
                    font_color,  # 字体颜色
                    outline_color,  # 描边颜色
                    bottom_margin,  # 底部边距
                ],
                outputs=[status_output, video_output],
                show_progress=True,  # 显示进度
            )

            # 发布到抖音
            Post_on_DY.click(
                auto_publishing_videos_DY,
                inputs=[video_output, two_line_input, pulish_with_cover],
                outputs=[status_output],
            )
            # 发布到小红书
            Post_on_XHS.click(
                auto_publishing_videos_XHS,
                inputs=[video_output, two_line_input, pulish_with_cover],
                outputs=[status_output],
            )

            # 发布到视频号
            Post_on_SPH.click(
                auto_publishing_videos_SPH,
                inputs=[video_output, two_line_input, pulish_with_cover],
                outputs=[status_output],
            )

            # 一键发布到抖音小红书视频号
            Post_on_ALL.click(
                auto_publishing_videos_ALL,
                inputs=[video_output, two_line_input, pulish_with_cover],
                outputs=[status_output],
            )

            # 更新确认界面
            with gr.Row(visible=False) as update_dialog:
                with gr.Column():
                    update_info = gr.Textbox(
                        label="更新信息", interactive=False, lines=8
                    )
                    with gr.Row():
                        confirm_btn = gr.Button("确认更新", variant="primary")
                        cancel_btn = gr.Button("取消")

            # 更新状态显示
            update_status = gr.Textbox(label="更新状态", interactive=False, lines=10)

            # 更新按钮
            update_elements_btn = gr.Button("检查更新")

            start_info = gr.Textbox(label="启动信息", interactive=False, lines=10)

            start_digit_human_button = gr.Button("启动digit_human")
            start_digit_human_button.click(
                start_digit_human,
                inputs=[account],
                outputs=[start_info],
            )
            start_cosyvoice_button = gr.Button("启动cosyvoice")
            start_cosyvoice_button.click(
                start_cosyvoice,
                inputs=[account],
                outputs=[start_info],
            )

            # 绑定事件
            update_elements_btn.click(
                fn=update_platform_elements, outputs=[update_info, update_dialog]
            )

            confirm_btn.click(fn=do_update, outputs=[update_status, update_dialog])

            cancel_btn.click(
                fn=cancel_update,  # 使用具名函数替代lambda
                outputs=[update_status, update_dialog],
            )

            # 保存API Key
            save_api_key_button.click(
                fn=save_api_key,
                inputs=[api_key_input],
                outputs=[status_output, api_key],  # 更新状态和下拉框
            )

            # 删除API Key
            delete_api_key_button.click(
                fn=delete_api_key,
                inputs=[api_key],
                outputs=[status_output, api_key],  # 更新状态和下拉框
            )

            # 刷新key
            refresh_api_key_button.click(fn=refresh_api_key, outputs=[api_key])

        # 添加一个说明文本，表明这是API服务
        gr.Markdown(
            """
        # API服务已启动
        此服务仅提供API访问，Web界面已禁用。
        """
        )
        
        # 移除特效字幕相关API接口
        #     )
        #     
        #     # 设置默认模板的API接口
        #     )
        #     
        #     # 获取默认模板的API接口
        #     )

    return demo
