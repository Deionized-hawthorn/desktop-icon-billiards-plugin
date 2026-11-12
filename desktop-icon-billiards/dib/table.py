"""Billiards physics for desktop icons, in desktop pixels.

The table is laid out inside the monitor work area, the white cue ball starts on
the left and the desktop icons are racked on the right. The caller aims with
:meth:`aim_at` and strikes with :meth:`shoot`; :meth:`step` advances the whole
simulation, including pocket exits and the ball-in-hand state after a scratch.
"""
import math
from collections import defaultdict
from dataclasses import replace

from .body import Body
from .shot import DEFAULT_FRICTION, ShotSettings

# How long a sinking icon keeps its exit animation.
EXIT_SECONDS = .62
LEGACY_MIN_POWER = .18
RAIL_REBOUND = .88
BALL_IMPULSE = .96
STOP_SPEED = .008
JUMP_GRAVITY = 22.  # Table heights per second squared.
SPIN_DECAY = 2.4


class BilliardsMotion:
    """Positions and physics of the white ball and the desktop icon rack."""

    def __init__(self, work_area, sizes, settings=None):
        self.sizes = sizes
        self.settings = settings if settings is not None else ShotSettings()
        # The game is always drawn directly on the desktop and always manual.
        self.desktop = True
        self.manual = True
        self.work_area = work_area
        left, top, right, bottom = work_area
        width = right - left
        height = bottom - top
        self.bounds = (round(left + width * .06), round(top + height * .09),
                       round(right - width * .06), round(bottom - height * .09))
        left, top, right, bottom = self.bounds
        self.width = right - left
        self.height = bottom - top
        mid = (left + right) / 2
        self.pockets = ((left, top), (mid, top), (right, top),
                        (left, bottom), (mid, bottom), (right, bottom))
        self.pocket_radius = min(49, max(18, self.height * .047))
        count = len(sizes)
        columns = max(1, math.ceil((math.sqrt(8 * count + 1) - 1) / 2))
        pitch = min(94, self.width * .45 / (columns + .5), self.height * .79 / columns)
        self.tile = min(64, pitch * .70)
        self.radius = pitch * .46
        self.white_radius = min(25, self.radius * .9)
        self.rack = []
        for column in range(columns):
            depth = min(column + 1, count - len(self.rack))
            for i in range(depth):
                x = left + self.width * .52 + column * pitch * .84
                y = (top + bottom) / 2 + (i - (depth - 1) / 2) * pitch * .95
                self.rack.append((x, y))
        # Counts every (re)started round so observers can tell rounds apart.
        self.round_serial = 0
        self.reset()

    def reset(self):
        left, top, _, bottom = self.bounds
        self.white = Body(left + self.width * .20, (top + bottom) / 2, self.white_radius, self.bounds)
        self.icons = [Body(x, y, self.radius, self.bounds) for x, y in self.rack]
        self.bodies = [self.white, *self.icons]
        self.sunk = set()
        self.white_sunk = False
        self.exits = {}
        self.state = 'ready'
        self.ready_for = 0.
        # The timed round runs from the first shot to the last icon sinking.
        self.round_serial += 1
        self.first_shot_at = None
        self.finished_at = None
        self.paused_at = None
        self.shots = 0
        self.used_custom_physics = False
        self.clock = 0.
        self.stroke = 0.
        self.power = 0.
        self.charge = LEGACY_MIN_POWER
        self._stroke_settings = self.settings
        self._preview_key = None
        self.aim_locked = False
        self.break_shot = True
        self.aim = self._aim()
        self.poses = self._poses()

    def active_bodies(self):
        return [body for index, body in enumerate(self.bodies) if index not in self.sunk]

    @property
    def pocketed_icons(self):
        return len(self.sunk) - (0 in self.sunk)

    @property
    def play_ms(self):
        """Whole milliseconds since the first shot; frozen once the table is cleared."""
        if self.first_shot_at is None:
            return 0
        end = self.finished_at if self.finished_at is not None else self.clock
        return max(0, round((end - self.first_shot_at) * 1000))

    @property
    def round_seconds(self):
        return self.play_ms // 1000

    def pause(self, now):
        """Freeze the round (the game is hidden). Nothing is simulated until :meth:`resume`."""
        if self.paused_at is None:
            self.paused_at = now

    def resume(self, now):
        """Continue after a pause; the hidden time does not count towards the round."""
        if self.paused_at is None:
            return
        gap = max(0., now - self.paused_at)
        if self.first_shot_at is not None and self.finished_at is None:
            self.first_shot_at += gap
        self.paused_at = None

    def _aim(self):
        x, y = self.white.x, self.white.y
        targets = [body for index, body in enumerate(self.icons, 1) if index not in self.sunk]
        target = min(targets, key=lambda body: (body.x - x) ** 2 + (body.y - y) ** 2, default=None)
        if target is None:
            return 1., 0.
        if self.break_shot:
            return 1., .022
        shot = self._pocket_shot(targets)
        dx, dy = (shot[0] - x, shot[1] - y) if shot else (target.x - x, target.y - y)
        distance = max(1, math.hypot(dx, dy))
        return dx / distance, dy / distance

    @staticmethod
    def _clear(x, y, tx, ty, others, radius):
        dx, dy = tx - x, ty - y
        length = dx * dx + dy * dy
        for other in others:
            t = max(0, min(1, ((other.x - x) * dx + (other.y - y) * dy) / max(1, length)))
            if math.hypot(other.x - x - t * dx, other.y - y - t * dy) < other.radius + radius:
                return False
        return True

    def _pocket_shot(self, targets):
        white = self.white
        left, top, right, bottom = self.bounds
        candidates = []
        for target in targets:
            for px, py in self.pockets:
                dx, dy = px - target.x, py - target.y
                distance = math.hypot(dx, dy)
                if distance < 1:
                    continue
                ux, uy = dx / distance, dy / distance
                contact = target.radius + white.radius
                gx, gy = target.x - ux * contact, target.y - uy * contact
                if not (left + white.radius <= gx <= right - white.radius
                        and top + white.radius <= gy <= bottom - white.radius):
                    continue
                wx, wy = gx - white.x, gy - white.y
                approach = math.hypot(wx, wy)
                alignment = (wx * ux + wy * uy) / max(1, approach)
                if alignment > .53:
                    candidates.append(((approach + distance) / alignment, target, px, py, gx, gy))
        for _, target, px, py, gx, gy in sorted(candidates, key=lambda shot: shot[0]):
            others = [body for body in targets if body is not target]
            if (self._clear(white.x, white.y, gx, gy, others, white.radius)
                    and self._clear(target.x, target.y, px, py, others, target.radius)):
                return gx, gy
        return None

    def aim_at(self, x, y):
        if self.state != 'ready' or self.aim_locked:
            return
        dx, dy = x - self.white.x, y - self.white.y
        length = math.hypot(dx, dy)
        if length > 2:
            self.aim = (dx / length, dy / length)

    def toggle_aim_lock(self):
        if self.aim_locked or self.state == 'ready':
            self.aim_locked = not self.aim_locked

    def shoot(self, power, now=None):
        """Strike the white ball. ``now`` is the frame clock; the first shot starts the round timer."""
        if self.state != 'ready' or power <= 0:
            return False
        self.state = 'stroke'
        self.stroke = 0.
        self.charge = min(1., power)
        self.power = self._shot_speed(self.charge)
        self._stroke_settings = self.settings
        if self.settings.friction != DEFAULT_FRICTION or self.settings.has_spin_or_elevation:
            self.used_custom_physics = True
        self.break_shot = False
        self.shots += 1
        if self.first_shot_at is None:
            self.first_shot_at = self.clock if now is None else now
            self.clock = max(self.clock, self.first_shot_at)
        return True

    def _shot_speed(self, power):
        power = max(0., min(1., power))
        # Ease into the original strength curve below its old minimum.
        return self.height * (.62 + 2.55 * power) * 1.58 * min(1., power / LEGACY_MIN_POWER)

    def _strike(self, body, speed, settings):
        dx, dy = self.aim
        elevation = math.radians(settings.elevation)
        downward = math.sin(elevation)
        forward_speed = speed * math.cos(elevation)
        body.vx, body.vy = dx * forward_speed, dy * forward_speed
        # A hard, downward hit rebounds from the cloth. A high tip position
        # makes a jump easier, while a low side hit can stay on the cloth.
        rebound = speed * downward * (.58 + settings.tip_y * .70)
        body.vz = max(0., rebound - self.height * .55)
        # The cloth converts off-centre spin to motion, including draw and
        # follow after a collision. With an elevated cue, side spin bends the path.
        follow = speed * .92 * settings.tip_y
        swerve = speed * 1.65 * settings.tip_x * downward ** 2
        body.spin_x = dx * follow - dy * swerve
        body.spin_y = dy * follow + dx * swerve
        body.side_spin = speed * settings.tip_x

    def cue(self):
        if self.state not in ('ready', 'stroke'):
            return None
        settings = self._stroke_settings if self.state == 'stroke' else self.settings
        dx, dy = self.aim
        projection = math.cos(math.radians(settings.elevation))
        pull = (12 + 34 * self.charge) * projection
        gap = pull * max(0, 1 - self.stroke / .082) if self.state == 'stroke' else pull
        side = self.white.radius * settings.tip_x
        setback = math.sqrt(self.white.radius ** 2 - side ** 2) + gap
        tip = self.white.x - dx * setback - dy * side, self.white.y - dy * setback + dx * side
        length = min(440, self.height * .48) * projection
        left, top, right, bottom = self.work_area
        for value, direction, low, high in ((tip[0], -dx, left + 5, right - 5),
                                            (tip[1], -dy, top + 5, bottom - 5)):
            if abs(direction) > 1e-6:
                edge = high if direction > 0 else low
                length = min(length, max(0, (edge - value) / direction))
        return tip, (tip[0] - dx * length, tip[1] - dy * length)

    def aim_guide(self):
        """Predict the opening shot and one outgoing leg per moving ball."""
        return self.aim_preview()[0]

    def aim_preview(self):
        """Return ``(lines, circles)``: the predicted paths and the collision circles to show faintly.

        Collisions use circles of ``self.radius``, a little larger than the drawn icon, so the
        ``ghost`` circle (the white ball at the moment of contact) and the ``target`` circle make
        the real contact point visible.
        """
        if self.state != 'ready' or not self.charge:
            return (), ()
        x, y, radius = self.white.x, self.white.y, self.white.radius
        dx, dy = self.aim
        speed = self._shot_speed(self.charge)
        targets = [body for index, body in enumerate(self.icons, 1) if index not in self.sunk]
        if self.settings.has_spin_or_elevation:
            key = (x, y, self.aim, speed, self.settings, tuple((body.x, body.y, body.radius) for body in targets))
            if key != self._preview_key:
                self._preview = self._spin_preview(speed, targets)
                self._preview_key = key
            return self._preview
        origin = x, y
        hit, kind, contact, velocity = self._guide_leg(origin, (dx * speed, dy * speed), radius, targets)
        lines = []
        gap = radius + 5
        if math.dist(origin, hit) > gap:
            lines.append(('incoming', (x + dx * gap, y + dy * gap), hit))
        vx, vy = velocity
        outgoing = []
        circles = []
        if kind == 'rail':
            hit_x, hit_y = contact
            rebound = (-vx * RAIL_REBOUND if hit_x else vx, -vy * RAIL_REBOUND if hit_y else vy)
            outgoing.append(('white', hit, rebound, radius, targets))
            circles.append(('ghost', hit, radius))
        elif kind == 'ball':
            target = contact
            target_pos = target.x, target.y
            separation = math.dist(hit, target_pos)
            circles.append(('ghost', hit, radius))
            circles.append(('target', target_pos, target.radius))
            if separation > 1e-6:
                nx, ny = (target.x - hit[0]) / separation, (target.y - hit[1]) / separation
                impulse = (vx * nx + vy * ny) * BALL_IMPULSE
                pushed = impulse * nx, impulse * ny
                other_targets = [body for body in targets if body is not target]
                outgoing.append(('white', hit, (vx - pushed[0], vy - pushed[1]), radius, other_targets))
                outgoing.append(('target', target_pos, pushed, target.radius, other_targets))
        for role, start, motion, size, obstacles in outgoing:
            end, _, _, _ = self._guide_leg(start, motion, size, obstacles)
            if math.dist(start, end) >= 2:
                lines.append((role, start, end))
        return tuple(lines), tuple(circles)

    def _spin_preview(self, speed, targets):
        """Trace a copy of the cue ball with the same flight, spin and contacts as a shot."""
        white = replace(self.white)
        obstacles = [replace(body) for body in targets]
        self._strike(white, speed, self.settings)
        lines, kind, target = self._trace_white(white, obstacles, 'incoming', white.radius + 5)
        circles = []
        if kind in ('rail', 'ball'):
            circles.append(('ghost', (white.x, white.y), white.radius))
            others = [body for body in obstacles if body is not target]
            white_path, _, _ = self._trace_white(white, others, 'white')
            lines.extend(white_path)
            if target is not None:
                origin = target.x, target.y
                circles.append(('target', origin, target.radius))
                end, _, _, _ = self._guide_leg(origin, (target.vx, target.vy), target.radius, others)
                if math.dist(origin, end) >= 2:
                    lines.append(('target', origin, end))
        return tuple(lines), tuple(circles)

    def _trace_white(self, white, obstacles, role, gap=0.):
        """Trace one leg, ending at a contact or when the cue ball stops."""
        drag = self.height * self.settings.friction
        spin_rate = SPIN_DECAY * math.sqrt(self.settings.friction / DEFAULT_FRICTION)
        speed = math.hypot(white.vx, white.vy) + math.hypot(white.spin_x, white.spin_y)
        dt = 1 / max(180, speed / max(.5, white.radius) * 1.7)
        decay = math.exp(-dt * spin_rate)
        start = white.x, white.y
        spacing = max(12., white.radius * .7)
        path = []
        steps = math.ceil(7 / dt)
        for i in range(steps):
            airborne = bool(white.z or white.vz)
            self._move_ball(white, dt)
            target = None
            kind = 'stop'
            if self._in_pocket(white) is not None:
                kind = 'pocket'
            elif self._walls(white):
                kind = 'rail'
            else:
                target = next((body for body in obstacles if self._collide(white, body)), None)
                if target is not None:
                    kind = 'ball'
                    self._walls(white)
            self._slow_ball(white, dt, drag, decay)
            end = white.x, white.y
            distance = math.dist(start, end)
            if gap and distance:
                consumed = min(gap, distance)
                fraction = consumed / distance
                start = (start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction)
                gap -= consumed
                distance -= consumed
            done = kind != 'stop' or not self._moving(white, drag, spin_rate) or i == steps - 1
            if done or distance >= spacing or airborne != bool(white.z or white.vz):
                if distance >= 1.:
                    path.append(('airborne' if airborne else role, start, end))
                start = end
            if done:
                break
        return path, kind, target

    def _guide_leg(self, origin, velocity, radius, obstacles):
        """Return endpoint, contact type, contact data and remaining velocity."""
        x, y = origin
        speed = math.hypot(*velocity)
        stop = self.height * STOP_SPEED
        if speed <= stop:
            return origin, 'stop', None, (0., 0.)
        dx, dy = velocity[0] / speed, velocity[1] / speed
        drag = self.height * self.settings.friction
        distance = (speed ** 2 - stop ** 2) / (2 * drag)
        kind, contact = 'stop', None
        left, top, right, bottom = self.bounds
        rail_x = ((right - radius if dx > 0 else left + radius) - x) / dx if abs(dx) > 1e-6 else math.inf
        rail_y = ((bottom - radius if dy > 0 else top + radius) - y) / dy if abs(dy) > 1e-6 else math.inf
        rail = min(rail_x, rail_y)
        if rail <= distance:
            distance = max(0., rail)
            kind = 'rail'
            contact = math.isclose(rail_x, rail, abs_tol=1e-6), math.isclose(rail_y, rail, abs_tol=1e-6)
        for body in obstacles:
            entry = self._ray_circle(x, y, dx, dy, body.x, body.y, radius + body.radius)
            if entry is not None and entry < distance:
                distance, kind, contact = entry, 'ball', body
        for px, py in self.pockets:
            entry = self._ray_circle(x, y, dx, dy, px, py, self.pocket_radius + radius * .55)
            if entry is not None and entry <= distance:
                distance, kind, contact = entry, 'pocket', None
        speed = math.sqrt(max(0., speed ** 2 - 2 * drag * distance))
        return (x + dx * distance, y + dy * distance), kind, contact, (dx * speed, dy * speed)

    @staticmethod
    def _ray_circle(x, y, dx, dy, cx, cy, radius):
        offset_x, offset_y = cx - x, cy - y
        forward = offset_x * dx + offset_y * dy
        across = offset_x * dy - offset_y * dx
        clearance = radius ** 2 - across ** 2
        if forward > 0 and clearance > 0:
            return max(0., forward - math.sqrt(clearance))
        return None

    def step(self, dt, now):
        """Advance the simulation with the runner's monotonic frame clock."""
        dt = max(0, min(.05, dt))
        if self.exits:
            self.exits = {i: (x, y, tx, ty, age + dt) for i, (x, y, tx, ty, age) in self.exits.items()
                          if age + dt < EXIT_SECONDS}
        if self.state == 'finished':
            return
        self.clock = now
        if self.state == 'return_white':
            self.ready_for += dt
            if self.ready_for >= .8:
                self.state = 'ball_in_hand'
                self._auto_place()
            return
        if self.state == 'ball_in_hand':
            return
        if self.state == 'ready':
            self.ready_for += dt
            return
        if self.state == 'stroke':
            self.stroke += dt
            if self.stroke < .082:
                return
            self._strike(self.white, self.power, self._stroke_settings)
            self.state = 'rolling'
            dt = self.stroke - .082
        drag = self.height * self._stroke_settings.friction
        spin_rate = SPIN_DECAY * math.sqrt(self._stroke_settings.friction / DEFAULT_FRICTION)
        speed = max((math.hypot(body.vx, body.vy) for body in self.active_bodies()), default=0)
        steps = max(1, math.ceil(dt * max(180, speed / max(.5, self.white_radius) * 1.7)))
        h = dt / steps
        spin_decay = math.exp(-h * spin_rate)
        for _ in range(steps):
            for index, body in enumerate(self.bodies):
                if index in self.sunk:
                    continue
                self._move_ball(body, h)
                pocket = self._in_pocket(body)
                if pocket is not None:
                    self.sunk.add(index)
                    if index == 0:
                        self.white_sunk = True
                    else:
                        self._start_exit(index, body, pocket)
                else:
                    self._walls(body)
            active = self.active_bodies()
            self._collisions(active)
            for body in active:
                self._walls(body)
                self._slow_ball(body, h, drag, spin_decay)
                body.impact *= math.exp(-h * 12)
                body.angle *= math.exp(-h * 4)
        cleared = self.pocketed_icons == len(self.icons)
        if cleared or not any(self._moving(body, drag, spin_rate) for body in self.active_bodies()):
            for body in self.bodies:
                body.vx = body.vy = body.impact = body.angle = 0.
                body.z = body.vz = body.spin_x = body.spin_y = body.side_spin = 0.
            self.ready_for = 0.
            if cleared:
                self.state = 'finished'
                self.finished_at = now
            elif self.white_sunk:
                self.state = 'return_white'
            else:
                self.state = 'ready'
                if not self.aim_locked:
                    self.aim = self._aim()
        self.poses = self._poses()

    def _move_ball(self, body, dt):
        body.x += body.vx * dt
        body.y += body.vy * dt
        if body.z or body.vz:
            gravity = self.height * JUMP_GRAVITY
            body.z += (body.vz - gravity * dt / 2) * dt
            body.vz -= gravity * dt
            if body.z <= 0 and body.vz <= 0:
                body.z = body.vz = 0.

    @staticmethod
    def _slow_ball(body, dt, drag, spin_decay):
        if body.z or body.vz:
            return
        body.vx += body.spin_x * (1 - spin_decay)
        body.vy += body.spin_y * (1 - spin_decay)
        body.spin_x *= spin_decay
        body.spin_y *= spin_decay
        body.side_spin *= spin_decay
        speed = math.hypot(body.vx, body.vy)
        if speed:
            remaining = max(0, 1 - drag * dt / speed)
            body.vx *= remaining
            body.vy *= remaining

    def _moving(self, body, drag, spin_rate):
        return (body.z > 0 or body.vz > 0 or math.hypot(body.vx, body.vy) >= self.height * STOP_SPEED
                or math.hypot(body.spin_x, body.spin_y) * spin_rate > drag)

    def _in_pocket(self, body):
        if body.z or body.vz:
            return None
        capture = self.pocket_radius + body.radius * .55
        return next(((x, y) for x, y in self.pockets
                     if (body.x - x) ** 2 + (body.y - y) ** 2 < capture * capture), None)

    def _start_exit(self, index, body, pocket):
        # The icon is drawn into the pocket centre, which always lies inside the work area.
        px, py = pocket
        self.exits[index] = (body.x, body.y, px, py, 0.)

    def exit_visual(self, index):
        """Return ``(x, y, fade, scale, spin)`` for a sinking icon, or None once it is gone.

        The icon slides to the pocket centre while shrinking and turning, then fades out.
        """
        exit_state = self.exits.get(index)
        if exit_state is None:
            return None
        x, y, tx, ty, age = exit_state
        progress = min(1., age / EXIT_SECONDS)
        slide = min(1., progress / .5)
        travel = slide * slide * (3 - 2 * slide)
        fade = max(0., min(1., (progress - .40) / .60))
        shrink = max(0., min(1., (progress - .10) / .80))
        scale = 1 - .70 * shrink * shrink * (3 - 2 * shrink)
        left, _, right, _ = self.work_area
        spin = (260 if tx < (left + right) / 2 else -260) * progress ** 2
        return x + (tx - x) * travel, y + (ty - y) * travel, fade, scale, spin

    def place_white(self, x, y):
        if self.state != 'ball_in_hand':
            return False
        left, top, right, bottom = self.bounds
        r = self.white.radius
        if not (left + r <= x <= right - r and top + r <= y <= bottom - r):
            return False
        if any(math.hypot(x - px, y - py) < self.pocket_radius + r for px, py in self.pockets):
            return False
        if any(math.hypot(x - body.x, y - body.y) < r + body.radius + 2 for body in self.active_bodies()):
            return False
        self.white.x = x
        self.white.y = y
        self.sunk.discard(0)
        self.white_sunk = False
        self.state = 'ready'
        self.ready_for = 0.
        if not self.aim_locked:
            self.aim = self._aim()
        return True

    def _auto_place(self):
        left, top, _, _ = self.bounds
        for fx in (.20, .31, .42, .54, .66, .78):
            for fy in (.5, .31, .69, .19, .81):
                if self.place_white(left + self.width * fx, top + self.height * fy):
                    return True
        return False

    def _walls(self, body):
        left, top, right, bottom = self.bounds
        bounced = False
        for axis, velocity, low, high in (('x', 'vx', left + body.radius, right - body.radius),
                                          ('y', 'vy', top + body.radius, bottom - body.radius)):
            position = getattr(body, axis)
            speed = getattr(body, velocity)
            if position < low or position > high:
                setattr(body, axis, max(low, min(high, position)))
                if (position < low and speed < 0) or (position > high and speed > 0):
                    setattr(body, velocity, -speed * RAIL_REBOUND)
                    body.impact = max(body.impact, min(.23, abs(speed) / self.height * .25))
                    bounced = True
                    if body.side_spin:
                        turn_limit = abs(speed) * .38
                        turn = math.copysign(1, speed) * max(-turn_limit, min(turn_limit, body.side_spin * .26))
                        if axis == 'x':
                            body.vy += turn
                        else:
                            body.vx -= turn
                        body.side_spin *= .55
        return bounced

    def _collisions(self, bodies):
        # Nearby buckets keep the number of tested pairs low on crowded desktops.
        cell = max(1, self.radius * 2)
        buckets = defaultdict(list)
        for body in bodies:
            gx = math.floor(body.x / cell)
            gy = math.floor(body.y / cell)
            for y in range(gy - 1, gy + 2):
                for x in range(gx - 1, gx + 2):
                    for other in buckets.get((x, y), ()):
                        self._collide(other, body)
            buckets[gx, gy].append(body)

    def _collide(self, a, b):
        dx = b.x - a.x
        dy = b.y - a.y
        limit = a.radius + b.radius
        contact_squared = limit ** 2 - (a.z - b.z) ** 2
        if dx * dx + dy * dy >= contact_squared:
            return False
        distance = math.hypot(dx, dy)
        nx, ny = (dx / distance, dy / distance) if distance > 1e-6 else (1., 0.)
        correction = (math.sqrt(contact_squared) - distance) * .5
        a.x -= nx * correction
        a.y -= ny * correction
        b.x += nx * correction
        b.y += ny * correction
        closing = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
        if closing >= 0:
            return False
        impulse = -closing * BALL_IMPULSE * (contact_squared / limit ** 2)
        a.vx -= nx * impulse
        a.vy -= ny * impulse
        b.vx += nx * impulse
        b.vy += ny * impulse
        impact = min(.23, impulse / self.height * .30)
        a.impact = max(a.impact, impact)
        b.impact = max(b.impact, impact)
        a.angle -= ny * impact * 95
        b.angle += ny * impact * 95
        return True

    def _poses(self):
        result = []
        for body, (w, h) in zip(self.icons, self.sizes):
            ratio = self.tile / max(w, h)
            result.append((body.x, body.y, max(1, round(w * ratio * (1 + body.impact * .64))),
                           max(1, round(h * ratio * (1 - body.impact))), body.angle, 0, 0.))
        return result
