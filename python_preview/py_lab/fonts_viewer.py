import pygame
import sys
import os

# 初始化Pygame
try:
    pygame.init()
except Exception as e:
    print(f"初始化Pygame时出错: {e}")
    sys.exit(1)

# 屏幕设置
WIDTH, HEIGHT = 1000, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("字体显示器 - 查看系统可用字体")
clock = pygame.time.Clock()
FPS = 60

# 颜色定义
BACKGROUND = (25, 25, 40)
PANEL_BG = (40, 40, 60)
TEXT_COLOR = (220, 220, 255)
HIGHLIGHT = (100, 200, 255)
SCROLLBAR = (80, 80, 120)
SCROLLBAR_HOVER = (100, 120, 180)


class FontDisplay:
    """字体显示器主类"""

    def __init__(self):
        self.fonts = []
        self.filtered_fonts = []
        self.current_index = 0
        self.scroll_offset = 0
        self.scroll_speed = 30
        self.font_size = 24
        self.sample_text = "Hello World! 你好，世界！ 1234567890"
        self.font_objects = {}
        self.font_preview_size = 36
        self.search_text = ""
        self.search_active = False

        # 尝试获取系统字体
        self.load_system_fonts()

        # 加载字体预览
        self.load_font_previews()

        # 计算字体列表区域
        self.list_area = pygame.Rect(20, 100, 350, HEIGHT - 140)
        self.preview_area = pygame.Rect(400, 100, WIDTH - 420, HEIGHT - 140)

        # 初始化界面字体
        self.init_ui_fonts()

    def load_system_fonts(self):
        """加载系统字体列表"""
        try:
            # 尝试获取系统字体列表
            self.fonts = pygame.font.get_fonts()
            print(f"找到 {len(self.fonts)} 种系统字体")
        except Exception as e:
            print(f"获取系统字体列表失败: {e}")
            print("尝试使用备用方法...")

            # 备用方法：使用默认字体和已知字体文件
            self.fonts = ["freesansbold", "freeserif", "None"]

            # 尝试常见系统字体路径
            common_font_paths = [
                # Windows
                "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\times.ttf",
                "C:\\Windows\\Fonts\\cour.ttf",
                # Linux
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                # macOS
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Times.ttc",
            ]

            for font_path in common_font_paths:
                if os.path.exists(font_path):
                    font_name = os.path.splitext(os.path.basename(font_path))[0]
                    self.fonts.append(font_path)
                    print(f"添加字体文件: {font_path}")

        # 如果没有找到字体，添加一个空条目
        if not self.fonts:
            self.fonts = ["无可用字体"]

        self.filtered_fonts = self.fonts.copy()

    def load_font_previews(self):
        """为每种字体创建预览对象"""
        self.font_objects = {}

        for i, font_name in enumerate(self.fonts):
            try:
                if font_name == "None":
                    # 使用Pygame默认字体
                    font_obj = pygame.font.Font(None, self.font_preview_size)
                    self.font_objects[font_name] = font_obj
                elif font_name.endswith((".ttf", ".ttc", ".otf")):
                    # 如果是字体文件路径
                    if os.path.exists(font_name):
                        font_obj = pygame.font.Font(font_name, self.font_preview_size)
                        self.font_objects[font_name] = font_obj
                else:
                    # 尝试使用系统字体名称
                    font_obj = pygame.font.SysFont(font_name, self.font_preview_size)
                    self.font_objects[font_name] = font_obj
            except Exception as e:
                # 如果创建字体失败，使用默认字体
                print(f"无法加载字体 '{font_name}': {e}")
                try:
                    font_obj = pygame.font.Font(None, self.font_preview_size)
                    self.font_objects[font_name] = font_obj
                except:
                    # 如果连默认字体都失败，标记为None
                    self.font_objects[font_name] = None

    def init_ui_fonts(self):
        """初始化UI字体"""
        try:
            # 尝试加载UI字体
            self.ui_font_small = pygame.font.Font(None, 20)
            self.ui_font_medium = pygame.font.Font(None, 24)
            self.ui_font_large = pygame.font.Font(None, 32)
        except:
            # 如果失败，创建一个简单的字体渲染函数
            print("UI字体初始化失败，将使用简单文本渲染")

            class SimpleFont:
                def __init__(self, size):
                    self.size = size
                    self.height = size

                def render(self, text, antialias, color):
                    # 创建一个简单的文本表面
                    width = len(text) * self.size // 2
                    surf = pygame.Surface((width, self.size), pygame.SRCALPHA)
                    # 这里只是占位，实际应该绘制文字
                    # 为了简单，我们只绘制一个矩形
                    pygame.draw.rect(surf, color, (0, 0, width, self.size), 1)
                    return surf

            self.ui_font_small = SimpleFont(20)
            self.ui_font_medium = SimpleFont(24)
            self.ui_font_large = SimpleFont(32)

    def filter_fonts(self):
        """根据搜索文本过滤字体"""
        if not self.search_text:
            self.filtered_fonts = self.fonts.copy()
        else:
            search_lower = self.search_text.lower()
            self.filtered_fonts = [
                font for font in self.fonts if search_lower in font.lower()
            ]

        # 确保索引有效
        if self.current_index >= len(self.filtered_fonts):
            self.current_index = max(0, len(self.filtered_fonts) - 1)

    def draw_font_list(self, surface):
        """绘制字体列表"""
        # 绘制列表背景
        pygame.draw.rect(surface, PANEL_BG, self.list_area, border_radius=8)
        pygame.draw.rect(surface, (60, 60, 80), self.list_area, 2, border_radius=8)

        # 绘制标题
        title_text = self.ui_font_medium.render(
            f"可用字体 ({len(self.filtered_fonts)}/{len(self.fonts)})",
            True,
            (200, 220, 255),
        )
        surface.blit(title_text, (self.list_area.x + 10, self.list_area.y - 30))

        # 计算可见范围
        font_height = 30
        visible_start = self.scroll_offset // font_height
        visible_count = self.list_area.height // font_height + 1

        # 确保不超出范围
        visible_start = max(
            0, min(visible_start, len(self.filtered_fonts) - visible_count)
        )

        # 绘制字体项
        for i in range(
            visible_start, min(visible_start + visible_count, len(self.filtered_fonts))
        ):
            font_name = self.filtered_fonts[i]
            y_pos = (
                self.list_area.y
                + (i - visible_start) * font_height
                - (self.scroll_offset % font_height)
            )

            # 检查是否在可视区域内
            if (
                y_pos < self.list_area.y
                or y_pos + font_height > self.list_area.y + self.list_area.height
            ):
                continue

            # 高亮当前选中的字体
            if i == self.current_index:
                pygame.draw.rect(
                    surface,
                    HIGHLIGHT,
                    (self.list_area.x, y_pos, self.list_area.width, font_height),
                )

            # 绘制字体名称
            font_display_name = (
                os.path.basename(font_name) if os.path.isfile(font_name) else font_name
            )
            if len(font_display_name) > 40:
                font_display_name = font_display_name[:37] + "..."

            font_text = self.ui_font_small.render(font_display_name, True, TEXT_COLOR)
            surface.blit(font_text, (self.list_area.x + 10, y_pos + 5))

            # 绘制序号
            index_text = self.ui_font_small.render(f"{i+1}.", True, (150, 150, 180))
            surface.blit(
                index_text, (self.list_area.x + self.list_area.width - 40, y_pos + 5)
            )

        # 绘制滚动条
        if len(self.filtered_fonts) * font_height > self.list_area.height:
            scrollbar_height = max(
                20,
                self.list_area.height
                * self.list_area.height
                / (len(self.filtered_fonts) * font_height),
            )
            scrollbar_y = (
                self.list_area.y
                + (self.scroll_offset / (len(self.filtered_fonts) * font_height))
                * self.list_area.height
            )

            scrollbar_rect = pygame.Rect(
                self.list_area.x + self.list_area.width - 10,
                scrollbar_y,
                8,
                scrollbar_height,
            )

            # 检查鼠标是否在滚动条上
            mouse_pos = pygame.mouse.get_pos()
            scrollbar_color = (
                SCROLLBAR_HOVER if scrollbar_rect.collidepoint(mouse_pos) else SCROLLBAR
            )

            pygame.draw.rect(surface, scrollbar_color, scrollbar_rect, border_radius=4)

    def draw_font_preview(self, surface):
        """绘制字体预览"""
        if not self.filtered_fonts:
            return

        current_font_name = self.filtered_fonts[self.current_index]

        # 绘制预览区域背景
        pygame.draw.rect(surface, PANEL_BG, self.preview_area, border_radius=8)
        pygame.draw.rect(surface, (60, 60, 80), self.preview_area, 2, border_radius=8)

        # 绘制字体名称标题
        font_title = f"预览: {current_font_name}"
        if len(font_title) > 60:
            font_title = font_title[:57] + "..."

        title_text = self.ui_font_medium.render(font_title, True, (200, 220, 255))
        surface.blit(title_text, (self.preview_area.x + 10, self.preview_area.y - 30))

        # 获取字体对象
        font_obj = self.font_objects.get(current_font_name)

        if font_obj is None:
            # 无法加载此字体
            error_text = self.ui_font_large.render(
                "无法加载此字体", True, (255, 100, 100)
            )
            surface.blit(
                error_text,
                (
                    self.preview_area.centerx - error_text.get_width() // 2,
                    self.preview_area.centery - 50,
                ),
            )

            # 显示字体文件路径（如果是文件路径）
            if os.path.isfile(current_font_name):
                path_text = self.ui_font_small.render(
                    f"路径: {current_font_name}", True, (200, 200, 200)
                )
                surface.blit(
                    path_text, (self.preview_area.x + 20, self.preview_area.centery)
                )

            return

        # 计算预览位置
        preview_x = self.preview_area.x + 20
        preview_y = self.preview_area.y + 20

        # 绘制不同大小的预览
        sizes = [24, 36, 48, 64]
        sample_texts = [
            "Hello World! 你好，世界！",
            "1234567890",
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "abcdefghijklmnopqrstuvwxyz",
            "!@#$%^&*()_+-=[]{}|;:,.<>?/",
        ]

        for i, size in enumerate(sizes):
            try:
                # 为每个尺寸创建字体对象
                if current_font_name == "None":
                    size_font = pygame.font.Font(None, size)
                elif current_font_name.endswith((".ttf", ".ttc", ".otf")):
                    size_font = pygame.font.Font(current_font_name, size)
                else:
                    size_font = pygame.font.SysFont(current_font_name, size)

                # 绘制尺寸标签
                size_label = self.ui_font_small.render(
                    f"{size}px:", True, (150, 200, 150)
                )
                surface.blit(size_label, (preview_x, preview_y))

                # 绘制示例文本
                sample_index = i % len(sample_texts)
                sample = sample_texts[sample_index]
                if len(sample) > 40:
                    sample = sample[:37] + "..."

                preview_text = size_font.render(sample, True, TEXT_COLOR)
                surface.blit(preview_text, (preview_x + 60, preview_y))

                preview_y += size + 10

                # 如果超出预览区域，停止绘制
                if preview_y > self.preview_area.y + self.preview_area.height - 50:
                    break

            except Exception as e:
                # 如果创建特定大小的字体失败，跳过
                continue

        # 绘制字体信息
        info_y = self.preview_area.y + self.preview_area.height - 80

        # 字体索引信息
        index_info = f"字体 {self.current_index + 1} / {len(self.filtered_fonts)}"
        index_text = self.ui_font_small.render(index_info, True, (180, 180, 220))
        surface.blit(index_text, (self.preview_area.x + 20, info_y))

        # 如果是字体文件，显示路径
        if os.path.isfile(current_font_name):
            try:
                file_size = os.path.getsize(current_font_name)
                size_mb = file_size / (1024 * 1024)
                size_info = f"文件大小: {size_mb:.2f} MB"
                size_text = self.ui_font_small.render(size_info, True, (180, 180, 220))
                surface.blit(size_text, (self.preview_area.x + 200, info_y))
            except:
                pass

    def draw_search_box(self, surface):
        """绘制搜索框"""
        search_rect = pygame.Rect(20, 50, 350, 30)

        # 绘制搜索框背景
        pygame.draw.rect(surface, PANEL_BG, search_rect, border_radius=4)
        pygame.draw.rect(
            surface,
            HIGHLIGHT if self.search_active else (100, 100, 120),
            search_rect,
            2,
            border_radius=4,
        )

        # 绘制搜索图标
        search_icon = self.ui_font_small.render("🔍", True, (150, 150, 180))
        surface.blit(search_icon, (search_rect.x + 8, search_rect.y + 5))

        # 绘制搜索文本
        search_text_display = self.search_text
        if not search_text_display and not self.search_active:
            search_text_display = "搜索字体..."

        text_color = (
            TEXT_COLOR if self.search_active or self.search_text else (100, 100, 120)
        )
        search_surface = self.ui_font_small.render(
            search_text_display, True, text_color
        )
        surface.blit(search_surface, (search_rect.x + 35, search_rect.y + 5))

        # 如果搜索文本太长，显示省略号
        if search_surface.get_width() > search_rect.width - 50:
            # 这里简化处理，实际应用中应该计算可见部分
            pass

    def draw_instructions(self, surface):
        """绘制操作说明"""
        instructions = [
            "操作说明:",
            "↑/↓: 选择字体  |  PageUp/PageDown: 快速滚动",
            "Home/End: 跳转到首/尾  |  Enter: 复制字体名称",
            "F5: 重新加载字体  |  ESC: 退出程序",
        ]

        y_pos = HEIGHT - 90
        for instruction in instructions:
            text = self.ui_font_small.render(instruction, True, (150, 180, 200))
            surface.blit(text, (20, y_pos))
            y_pos += 25

    def draw(self, surface):
        """绘制整个界面"""
        # 清屏
        surface.fill(BACKGROUND)

        # 绘制标题
        title = self.ui_font_large.render(
            "字体显示器 - 查看系统可用字体", True, (220, 240, 255)
        )
        surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 10))

        # 绘制搜索框
        self.draw_search_box(surface)

        # 绘制字体列表
        self.draw_font_list(surface)

        # 绘制字体预览
        self.draw_font_preview(surface)

        # 绘制操作说明
        self.draw_instructions(surface)

    def handle_events(self):
        """处理事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False

                elif event.key == pygame.K_F5:
                    # 重新加载字体
                    self.load_system_fonts()
                    self.load_font_previews()
                    self.filter_fonts()
                    print("已重新加载字体")

                elif event.key == pygame.K_RETURN:
                    # 复制当前字体名称到剪贴板
                    if self.filtered_fonts:
                        font_name = self.filtered_fonts[self.current_index]
                        pygame.scrap.put(pygame.SCRAP_TEXT, font_name.encode())
                        print(f"已复制字体名称: {font_name}")

                elif self.search_active:
                    # 搜索框激活时的键盘处理
                    if event.key == pygame.K_BACKSPACE:
                        self.search_text = self.search_text[:-1]
                        self.filter_fonts()
                    elif event.key == pygame.K_ESCAPE:
                        self.search_active = False
                    elif event.unicode.isprintable():
                        self.search_text += event.unicode
                        self.filter_fonts()

                else:
                    # 非搜索模式下的键盘控制
                    if event.key == pygame.K_UP:
                        self.current_index = max(0, self.current_index - 1)
                        self.ensure_visible()
                    elif event.key == pygame.K_DOWN:
                        self.current_index = min(
                            len(self.filtered_fonts) - 1, self.current_index + 1
                        )
                        self.ensure_visible()
                    elif event.key == pygame.K_PAGEUP:
                        self.current_index = max(0, self.current_index - 10)
                        self.ensure_visible()
                    elif event.key == pygame.K_PAGEDOWN:
                        self.current_index = min(
                            len(self.filtered_fonts) - 1, self.current_index + 10
                        )
                        self.ensure_visible()
                    elif event.key == pygame.K_HOME:
                        self.current_index = 0
                        self.ensure_visible()
                    elif event.key == pygame.K_END:
                        self.current_index = len(self.filtered_fonts) - 1
                        self.ensure_visible()
                    elif (
                        event.key == pygame.K_s
                        and pygame.key.get_mods() & pygame.KMOD_CTRL
                    ):
                        # Ctrl+S 激活搜索
                        self.search_active = True
                    elif event.key == pygame.K_F1:
                        # 显示帮助
                        self.show_help()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = pygame.mouse.get_pos()

                # 检查是否点击了搜索框
                search_rect = pygame.Rect(20, 50, 350, 30)
                if search_rect.collidepoint(mouse_pos):
                    self.search_active = True
                else:
                    self.search_active = False

                # 检查是否点击了字体列表
                if self.list_area.collidepoint(mouse_pos):
                    font_height = 30
                    visible_start = self.scroll_offset // font_height
                    click_index = (
                        visible_start
                        + (
                            mouse_pos[1]
                            - self.list_area.y
                            + (self.scroll_offset % font_height)
                        )
                        // font_height
                    )

                    if 0 <= click_index < len(self.filtered_fonts):
                        self.current_index = click_index

                # 鼠标滚轮滚动
                if event.button == 4:  # 向上滚动
                    self.scroll_offset = max(0, self.scroll_offset - self.scroll_speed)
                elif event.button == 5:  # 向下滚动
                    max_scroll = max(
                        0, len(self.filtered_fonts) * 30 - self.list_area.height
                    )
                    self.scroll_offset = min(
                        max_scroll, self.scroll_offset + self.scroll_speed
                    )

        return True

    def ensure_visible(self):
        """确保当前选中的字体在可视区域内"""
        font_height = 30
        item_top = self.current_index * font_height
        item_bottom = (self.current_index + 1) * font_height

        if item_top < self.scroll_offset:
            self.scroll_offset = item_top
        elif item_bottom > self.scroll_offset + self.list_area.height:
            self.scroll_offset = item_bottom - self.list_area.height

    def show_help(self):
        """显示帮助信息（控制台）"""
        print("\n" + "=" * 50)
        print("字体显示器 - 帮助信息")
        print("=" * 50)
        print("1. 使用上下箭头键选择字体")
        print("2. 使用PageUp/PageDown快速滚动")
        print("3. 使用Home/End跳转到列表首尾")
        print("4. 点击搜索框或按Ctrl+S激活搜索")
        print("5. 按Enter复制当前字体名称")
        print("6. 按F5重新加载字体列表")
        print("7. 按F1显示此帮助")
        print("8. 按ESC退出程序")
        print("=" * 50 + "\n")

    def run(self):
        """运行主循环"""
        running = True

        # 显示初始帮助
        self.show_help()
        print(f"找到 {len(self.fonts)} 种字体")
        if self.fonts:
            print(f"第一个字体: {self.fonts[0]}")
            if len(self.fonts) > 1:
                print(f"最后一个字体: {self.fonts[-1]}")

        while running:
            running = self.handle_events()

            # 绘制界面
            self.draw(screen)

            # 更新显示
            pygame.display.flip()
            clock.tick(FPS)

        pygame.quit()
        sys.exit()


def main():
    """主函数"""
    print("启动字体显示器...")
    print("正在加载系统字体，请稍候...")

    try:
        app = FontDisplay()
        app.run()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback

        traceback.print_exc()
        pygame.quit()
        sys.exit(1)


if __name__ == "__main__":
    main()
