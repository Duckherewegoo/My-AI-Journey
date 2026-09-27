import pygame
import sys
import math
import random

# 初始化pygame
pygame.init()

# 游戏窗口设置
WIDTH, HEIGHT = 1000, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("愤怒的小鸟 - 简化版")

# 颜色定义
BACKGROUND = (135, 206, 235)  # 天空蓝
GROUND_COLOR = (124, 252, 0)  # 草地绿
SLINGSHOT_COLOR = (139, 69, 19)  # 棕色
BIRD_COLOR = (255, 0, 0)  # 红色小鸟
PIG_COLOR = (0, 128, 0)  # 绿色猪猪
BLOCK_COLOR = (160, 82, 45)  # 木块棕色
TEXT_COLOR = (255, 255, 255)  # 白色文字
TRAJECTORY_COLOR = (255, 255, 255, 128)  # 半白轨迹线

# 游戏参数
GRAVITY = 0.5
ELASTICITY = 0.8  # 弹性系数
GROUND_HEIGHT = 100
FPS = 60
clock = pygame.time.Clock()


class Bird:
    """小鸟类"""

    def __init__(self, x, y, radius=15):
        self.x = x
        self.y = y
        self.radius = radius
        self.vx = 0
        self.vy = 0
        self.is_loaded = True  # 是否在弹弓上
        self.is_flying = False  # 是否在飞行中
        self.is_active = True  # 是否活跃（未被销毁）
        self.dragging = False
        self.trajectory_points = []

    def update(self):
        """更新小鸟位置和速度"""
        if not self.is_active:
            return

        if self.is_flying:
            # 应用重力
            self.vy += GRAVITY

            # 更新位置
            self.x += self.vx
            self.y += self.vy

            # 检查是否落地
            if self.y >= HEIGHT - GROUND_HEIGHT - self.radius:
                self.y = HEIGHT - GROUND_HEIGHT - self.radius
                self.vy = -self.vy * ELASTICITY
                self.vx *= ELASTICITY

                # 如果速度很小，停止运动
                if abs(self.vx) < 0.5 and abs(self.vy) < 0.5:
                    self.is_flying = False
                    self.vx = 0
                    self.vy = 0

            # 检查是否飞出屏幕
            if (
                self.x < -self.radius
                or self.x > WIDTH + self.radius
                or self.y < -self.radius
            ):
                self.is_active = False

    def draw(self, surface):
        """绘制小鸟"""
        if not self.is_active:
            return

        pygame.draw.circle(surface, BIRD_COLOR, (int(self.x), int(self.y)), self.radius)
        # 绘制眼睛
        eye_radius = self.radius // 3
        eye_x = int(self.x + self.radius // 2)
        eye_y = int(self.y - self.radius // 2)
        pygame.draw.circle(surface, (255, 255, 255), (eye_x, eye_y), eye_radius)
        pygame.draw.circle(surface, (0, 0, 0), (eye_x, eye_y), eye_radius // 2)

        # 绘制鸟喙
        beak_points = [
            (int(self.x + self.radius), int(self.y)),
            (int(self.x + self.radius + self.radius // 2), int(self.y)),
            (int(self.x + self.radius), int(self.y + self.radius // 3)),
        ]
        pygame.draw.polygon(surface, (255, 165, 0), beak_points)

    def launch(self, power, angle):
        """发射小鸟"""
        self.vx = power * math.cos(angle)
        self.vy = -power * math.sin(angle)
        self.is_loaded = False
        self.is_flying = True

    def calculate_trajectory(self, start_x, start_y, power, angle, steps=30):
        """计算轨迹点"""
        self.trajectory_points = []
        dt = 0.5
        vx = power * math.cos(angle)
        vy = -power * math.sin(angle)
        x, y = start_x, start_y

        for _ in range(steps):
            x += vx * dt
            y += vy * dt
            vy += GRAVITY * dt

            # 如果碰到地面，停止计算
            if y >= HEIGHT - GROUND_HEIGHT - self.radius:
                y = HEIGHT - GROUND_HEIGHT - self.radius
                break

            self.trajectory_points.append((int(x), int(y)))


class Pig:
    """猪猪类"""

    def __init__(self, x, y, radius=20):
        self.x = x
        self.y = y
        self.radius = radius
        self.is_alive = True

    def draw(self, surface):
        """绘制猪猪"""
        if not self.is_alive:
            return

        pygame.draw.circle(surface, PIG_COLOR, (int(self.x), int(self.y)), self.radius)
        # 绘制眼睛
        eye_radius = self.radius // 4
        eye_x1 = int(self.x - self.radius // 3)
        eye_x2 = int(self.x + self.radius // 3)
        eye_y = int(self.y - self.radius // 3)
        pygame.draw.circle(surface, (255, 255, 255), (eye_x1, eye_y), eye_radius)
        pygame.draw.circle(surface, (255, 255, 255), (eye_x2, eye_y), eye_radius)
        pygame.draw.circle(surface, (0, 0, 0), (eye_x1, eye_y), eye_radius // 2)
        pygame.draw.circle(surface, (0, 0, 0), (eye_x2, eye_y), eye_radius // 2)

        # 绘制鼻孔
        nose_y = int(self.y + self.radius // 4)
        pygame.draw.circle(surface, (255, 192, 203), (eye_x1, nose_y), eye_radius // 2)
        pygame.draw.circle(surface, (255, 192, 203), (eye_x2, nose_y), eye_radius // 2)


class Block:
    """障碍物（木块）类"""

    def __init__(self, x, y, width=40, height=40):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.health = 2
        self.is_alive = True

    def draw(self, surface):
        """绘制障碍物"""
        if not self.is_alive:
            return

        # 根据生命值改变颜色深浅
        color_factor = 0.5 + (self.health / 4.0)
        color = (
            int(BLOCK_COLOR[0] * color_factor),
            int(BLOCK_COLOR[1] * color_factor),
            int(BLOCK_COLOR[2] * color_factor),
        )

        pygame.draw.rect(
            surface,
            color,
            (
                int(self.x - self.width / 2),
                int(self.y - self.height / 2),
                self.width,
                self.height,
            ),
        )
        # 绘制木纹
        pygame.draw.rect(
            surface,
            (color[0] - 20, color[1] - 20, color[2] - 20),
            (
                int(self.x - self.width / 2),
                int(self.y - self.height / 2),
                self.width,
                5,
            ),
        )


class Slingshot:
    """弹弓类"""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.width = 20
        self.height = 100

    def draw(self, surface, bird=None):
        """绘制弹弓"""
        # 绘制弹弓支架
        pygame.draw.rect(
            surface,
            SLINGSHOT_COLOR,
            (self.x - self.width // 2, self.y, self.width, self.height),
        )

        # 绘制弹弓叉
        fork_height = 60
        fork_width = 40
        left_fork_x = self.x - fork_width
        right_fork_x = self.x + fork_width

        # 绘制弹弓叉
        pygame.draw.line(
            surface,
            SLINGSHOT_COLOR,
            (left_fork_x, self.y + 20),
            (left_fork_x, self.y + fork_height),
            5,
        )
        pygame.draw.line(
            surface,
            SLINGSHOT_COLOR,
            (right_fork_x, self.y + 20),
            (right_fork_x, self.y + fork_height),
            5,
        )

        # 如果小鸟在弹弓上，绘制弹弓带
        if bird and bird.is_loaded and bird.is_active:
            pygame.draw.line(
                surface,
                SLINGSHOT_COLOR,
                (left_fork_x, self.y + fork_height // 2),
                (bird.x, bird.y),
                3,
            )
            pygame.draw.line(
                surface,
                SLINGSHOT_COLOR,
                (right_fork_x, self.y + fork_height // 2),
                (bird.x, bird.y),
                3,
            )


class Game:
    """游戏主类"""

    def __init__(self):
        self.slingshot = Slingshot(150, HEIGHT - GROUND_HEIGHT - 50)
        self.birds = []
        self.pigs = []
        self.blocks = []
        self.score = 0
        self.birds_count = 5
        self.level = 1
        self.game_over = False
        self.level_complete = False
        self.dragging = False
        self.drag_start_pos = (0, 0)

        # 初始化游戏对象
        self.reset_level()

    def reset_level(self):
        """重置关卡"""
        # 创建小鸟
        self.birds = []
        bird = Bird(self.slingshot.x, self.slingshot.y)
        self.birds.append(bird)

        # 创建猪猪
        self.pigs = []
        pig_positions = [
            (WIDTH - 200, HEIGHT - GROUND_HEIGHT - 30),
            (WIDTH - 300, HEIGHT - GROUND_HEIGHT - 100),
            (WIDTH - 400, HEIGHT - GROUND_HEIGHT - 30),
        ]

        for pos in pig_positions[: min(self.level + 1, 3)]:
            self.pigs.append(Pig(pos[0], pos[1]))

        # 创建障碍物
        self.blocks = []
        for i in range(self.level + 2):
            x = WIDTH - 250 - i * 60
            y = HEIGHT - GROUND_HEIGHT - 100
            self.blocks.append(Block(x, y))

        self.level_complete = False

    def handle_events(self):
        """处理游戏事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:  # 按R重置游戏
                    self.__init__()
                elif (
                    event.key == pygame.K_SPACE and self.level_complete
                ):  # 空格键进入下一关
                    self.level += 1
                    self.birds_count = 5
                    self.reset_level()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # 左键
                    mouse_x, mouse_y = pygame.mouse.get_pos()
                    current_bird = self.get_current_bird()

                    # 如果点击了当前小鸟
                    if (
                        current_bird
                        and current_bird.is_loaded
                        and math.sqrt(
                            (mouse_x - current_bird.x) ** 2
                            + (mouse_y - current_bird.y) ** 2
                        )
                        < current_bird.radius
                    ):
                        self.dragging = True
                        self.drag_start_pos = (mouse_x, mouse_y)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and self.dragging:  # 左键释放
                    self.dragging = False
                    current_bird = self.get_current_bird()

                    if current_bird and current_bird.is_loaded:
                        mouse_x, mouse_y = pygame.mouse.get_pos()

                        # 计算发射力度和角度
                        dx = self.drag_start_pos[0] - mouse_x
                        dy = self.drag_start_pos[1] - mouse_y
                        power = min(
                            math.sqrt(dx * dx + dy * dy) / 10, 20
                        )  # 限制最大力度
                        angle = math.atan2(dy, dx) if dx != 0 else math.pi / 2

                        # 发射小鸟
                        current_bird.launch(power, angle)

                        # 减少小鸟数量
                        self.birds_count -= 1

    def get_current_bird(self):
        """获取当前可用的鸟（在弹弓上或下一个）"""
        for bird in self.birds:
            if bird.is_active and bird.is_loaded:
                return bird

        # 如果没有在弹弓上的鸟，但还有剩余鸟数量，创建新鸟
        if self.birds_count > 0 and not any(b.is_loaded for b in self.birds):
            new_bird = Bird(self.slingshot.x, self.slingshot.y)
            self.birds.append(new_bird)
            return new_bird

        return None

    def update(self):
        """更新游戏状态"""
        if self.game_over or self.level_complete:
            return

        # 更新所有小鸟
        for bird in self.birds:
            bird.update()

            # 如果小鸟停止运动且不在弹弓上，检查是否需要新鸟
            if not bird.is_flying and not bird.is_loaded and bird.is_active:
                # 延迟一点时间后，如果还有剩余鸟，加载新鸟
                if self.birds_count > 0:
                    # 这里简化处理：直接创建新鸟
                    pass

        # 检查碰撞
        self.check_collisions()

        # 检查关卡是否完成
        if all(not pig.is_alive for pig in self.pigs):
            self.level_complete = True
            self.score += 100 * self.level

        # 检查游戏是否结束
        if (
            self.birds_count <= 0
            and not any(
                bird.is_active and (bird.is_flying or bird.is_loaded)
                for bird in self.birds
            )
            and any(pig.is_alive for pig in self.pigs)
        ):
            self.game_over = True

    def check_collisions(self):
        """检查所有碰撞"""
        for bird in self.birds:
            if not bird.is_active or not bird.is_flying:
                continue

            # 小鸟与猪猪的碰撞
            for pig in self.pigs:
                if pig.is_alive:
                    dx = bird.x - pig.x
                    dy = bird.y - pig.y
                    distance = math.sqrt(dx * dx + dy * dy)

                    if distance < bird.radius + pig.radius:
                        pig.is_alive = False
                        bird.is_active = False
                        self.score += 50

            # 小鸟与障碍物的碰撞
            for block in self.blocks:
                if block.is_alive:
                    # 简单的矩形与圆形碰撞检测
                    closest_x = max(
                        block.x - block.width / 2,
                        min(bird.x, block.x + block.width / 2),
                    )
                    closest_y = max(
                        block.y - block.height / 2,
                        min(bird.y, block.y + block.height / 2),
                    )

                    dx = bird.x - closest_x
                    dy = bird.y - closest_y

                    if dx * dx + dy * dy < bird.radius * bird.radius:
                        block.health -= 1
                        if block.health <= 0:
                            block.is_alive = False

                        # 简单的碰撞反弹
                        if abs(dx) > abs(dy):
                            bird.vx = -bird.vx * ELASTICITY
                        else:
                            bird.vy = -bird.vy * ELASTICITY

                        # 稍微移动小鸟避免卡住
                        bird.x += bird.vx * 0.1
                        bird.y += bird.vy * 0.1

    def draw(self, surface):
        """绘制游戏"""
        # 绘制背景
        surface.fill(BACKGROUND)

        # 绘制地面
        pygame.draw.rect(
            surface, GROUND_COLOR, (0, HEIGHT - GROUND_HEIGHT, WIDTH, GROUND_HEIGHT)
        )

        # 绘制弹弓
        self.slingshot.draw(surface, self.get_current_bird())

        # 绘制障碍物
        for block in self.blocks:
            block.draw(surface)

        # 绘制猪猪
        for pig in self.pigs:
            pig.draw(surface)

        # 绘制小鸟
        for bird in self.birds:
            bird.draw(surface)

            # 如果正在拖动小鸟，绘制轨迹线
            if self.dragging and bird.is_loaded:
                mouse_x, mouse_y = pygame.mouse.get_pos()
                dx = self.drag_start_pos[0] - mouse_x
                dy = self.drag_start_pos[1] - mouse_y
                power = min(math.sqrt(dx * dx + dy * dy) / 10, 20)
                angle = math.atan2(dy, dx) if dx != 0 else math.pi / 2

                bird.calculate_trajectory(bird.x, bird.y, power, angle)

                # 绘制轨迹点
                for point in bird.trajectory_points:
                    pygame.draw.circle(surface, TRAJECTORY_COLOR, point, 3)

        # 绘制分数和小鸟数量
        font = pygame.font.SysFont(None, 36)
        score_text = font.render(f"分数: {self.score}", True, TEXT_COLOR)
        birds_text = font.render(f"剩余小鸟: {self.birds_count}", True, TEXT_COLOR)
        level_text = font.render(f"关卡: {self.level}", True, TEXT_COLOR)

        surface.blit(score_text, (10, 10))
        surface.blit(birds_text, (10, 50))
        surface.blit(level_text, (10, 90))

        # 绘制操作提示
        help_font = pygame.font.SysFont(None, 24)
        help_text = help_font.render(
            "操作: 拖动小鸟发射, R键重置游戏", True, TEXT_COLOR
        )
        surface.blit(help_text, (WIDTH - 300, 10))

        # 绘制游戏结束或关卡完成信息
        if self.game_over:
            game_over_font = pygame.font.SysFont(None, 72)
            game_over_text = game_over_font.render("游戏结束!", True, (255, 0, 0))
            restart_text = font.render("按R键重新开始", True, TEXT_COLOR)

            text_rect = game_over_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 50))
            surface.blit(game_over_text, text_rect)

            text_rect = restart_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 20))
            surface.blit(restart_text, text_rect)

        elif self.level_complete:
            complete_font = pygame.font.SysFont(None, 72)
            complete_text = complete_font.render(
                f"关卡 {self.level} 完成!", True, (0, 255, 0)
            )
            next_text = font.render("按空格键进入下一关", True, TEXT_COLOR)
            score_add_text = font.render(f"+{100 * self.level} 分", True, (255, 255, 0))

            text_rect = complete_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 50))
            surface.blit(complete_text, text_rect)

            text_rect = score_add_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 10))
            surface.blit(score_add_text, text_rect)

            text_rect = next_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 60))
            surface.blit(next_text, text_rect)

        # 绘制发射力度指示器（如果正在拖动）
        if self.dragging:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            current_bird = self.get_current_bird()

            if current_bird:
                dx = self.drag_start_pos[0] - mouse_x
                dy = self.drag_start_pos[1] - mouse_y
                power = min(math.sqrt(dx * dx + dy * dy) / 10, 20)

                # 绘制力度条
                pygame.draw.rect(
                    surface,
                    (255, 255, 255),
                    (self.drag_start_pos[0] - 50, self.drag_start_pos[1] - 30, 100, 20),
                )
                pygame.draw.rect(
                    surface,
                    (255, 0, 0),
                    (
                        self.drag_start_pos[0] - 50,
                        self.drag_start_pos[1] - 30,
                        power * 5,
                        20,
                    ),
                )

                # 绘制力度值
                power_font = pygame.font.SysFont(None, 24)
                power_text = power_font.render(f"力度: {power:.1f}", True, (0, 0, 0))
                surface.blit(
                    power_text,
                    (self.drag_start_pos[0] - 30, self.drag_start_pos[1] - 30),
                )


def main():
    """游戏主函数"""
    game = Game()

    # 游戏主循环
    while True:
        # 处理事件
        game.handle_events()

        # 更新游戏状态
        game.update()

        # 绘制游戏
        game.draw(screen)

        # 更新显示
        pygame.display.flip()

        # 控制帧率
        clock.tick(FPS)


if __name__ == "__main__":
    main()
