from dataclasses import dataclass, asdict, fields
import math

TYPES = {'spur': 'Прямозубая', 'helical': 'Косозубая', 'herringbone': 'Шевронная',
         'internal': 'Внутреннее зацепление', 'rack': 'Зубчатая рейка',
         'bevel': 'Коническая · эскиз', 'worm': 'Червяк · винт'}

@dataclass
class Parameters:
    kind: str = 'helical'
    teeth: int = 48
    module: float = 0.5280927299414034
    sizing: str = 'module'
    outside: float = 28.031443620351585
    height: float = 10.0
    pressure: float = 20.0
    helix: float = 20.0
    hand: str = 'right'
    backlash: float = 0.10
    root_override: float = 0.0
    bore: float = 2.8
    bore_shape: str = 'round'
    flat: float = 0.5
    counterbore: float = 10.0
    counter_depth: float = 5.0
    rim: float = 3.0
    cone: float = 15.0
    starts: int = 1
    worm_diameter: float = 16.0
    quality: str = 'fine'

    def dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        allowed = {f.name for f in fields(cls)}
        if not isinstance(data, dict) or any(k not in allowed for k in data):
            raise ValueError('Неизвестный формат параметров')
        p = cls(**data)
        p.dimensions()
        return p

    def dimensions(self):
        for k, v in self.dict().items():
            if isinstance(v, (int, float)) and (not math.isfinite(v) or abs(v) > 1e6):
                raise ValueError('Недопустимое число: ' + k)
        if self.kind not in TYPES or self.hand not in ('left', 'right') or self.sizing not in ('module', 'outside'):
            raise ValueError('Неизвестный тип шестерни или способ задания размера')
        if self.bore_shape not in ('round', 'hex', 'd') or self.quality not in ('draft', 'fine', 'ultra'):
            raise ValueError('Неизвестная форма отверстия или точность')
        if int(self.teeth) != self.teeth or not 6 <= self.teeth <= 300:
            raise ValueError('Количество зубьев: от 6 до 300')
        if not 0.2 <= self.height <= 300 or not 10 <= self.pressure <= 35:
            raise ValueError('Высота: 0,2–300 мм; угол профиля: 10–35°')
        if not 0 <= self.helix <= 50 or min(self.bore, self.counterbore, self.counter_depth, self.backlash, self.root_override) < 0:
            raise ValueError('Угол наклона: 0–50°; размеры не могут быть отрицательными')
        beta = math.radians(self.helix if self.kind in ('helical', 'herringbone', 'internal') else 0)
        c = math.cos(beta)
        m = self.module
        if self.sizing == 'outside' and self.kind not in ('internal', 'rack', 'worm'):
            m = self.outside / (self.teeth/c + 2)
        if not 0.05 <= m <= 20:
            raise ValueError('Модуль должен быть в пределах 0,05–20 мм')
        rp = m*self.teeth/(2*c)
        alpha = math.atan(math.tan(math.radians(self.pressure))/c)
        rb = rp*math.cos(alpha)
        ra, rf = rp+m, rp-1.25*m
        if self.root_override and self.kind not in ('internal', 'rack', 'worm'):
            rf = self.root_override/2
        if self.kind == 'internal':
            ra, rf = rp-m, rp+1.25*m
            if ra <= rb:
                raise ValueError('Внутренняя шестерня: увеличьте число зубьев или угол профиля (вершина ниже основной окружности)')
            if self.rim < 0.5:
                raise ValueError('Толщина обода должна быть не менее 0,5 мм')
        if self.kind == 'worm':
            ra = self.worm_diameter/2
            rf = ra-2.25*m
            rp = ra-m
            if not 1 <= self.starts <= 8 or int(self.starts) != self.starts:
                raise ValueError('Число заходов червяка: от 1 до 8')
        if rf <= 0 or (self.kind != 'internal' and rf >= ra):
            raise ValueError('Диаметр впадин должен быть положительным и меньше наружного')
        halfbase = math.pi/(2*self.teeth)+math.tan(alpha)-alpha-self.backlash/(2*rp)
        tipinv = math.sqrt(max(0,(ra/rb)**2-1))
        tiphalf = halfbase-tipinv+math.atan(tipinv)
        if self.kind not in ('internal','rack','worm') and tiphalf <= 0.001:
            raise ValueError('Вершина зуба исчезла: уменьшите боковой зазор или измените размеры')
        ts = math.sqrt(max(0,(rf/rb)**2-1))
        if self.kind not in ('internal','rack','worm') and halfbase-ts+math.atan(ts) >= math.pi/self.teeth:
            raise ValueError('Зубья пересекаются у корня: увеличьте диаметр впадин или задайте 0 для стандартного')
        if self.kind=='rack' and math.pi*m/4-m*math.tan(math.radians(self.pressure))-self.backlash/2<=0:
            raise ValueError('Вершина зуба рейки исчезла: уменьшите боковой зазор')
        if self.kind == 'internal':
            root_half = math.pi/(2*self.teeth)-(math.tan(alpha)-alpha)+math.sqrt((rf/rb)**2-1)-math.acos(rb/rf)-self.backlash/(2*rp)
            if root_half >= math.pi/self.teeth:
                raise ValueError('Во внутреннем профиле исчезла впадина: уменьшите зазор')
            tip_half = math.pi/(2*self.teeth)-(math.tan(alpha)-alpha)+math.sqrt((ra/rb)**2-1)-math.acos(rb/ra)-self.backlash/(2*rp)
            if tip_half<=0.0001:
                raise ValueError('Вершина внутреннего зуба исчезла: уменьшите зазор')
        scale = 1.0
        if self.kind == 'bevel':
            if not 1 <= self.cone <= 45:
                raise ValueError('Угол конуса: 1–45°')
            scale = 1-self.height*math.tan(math.radians(self.cone))/rp
            if scale <= 0.15:
                raise ValueError('Слишком высокий конус: уменьшите высоту или угол конуса')
        counter = self.counterbore > 0 and self.counter_depth > 0 and self.kind not in ('internal','rack')
        if counter and self.counter_depth >= self.height:
            raise ValueError('Глубина расточки должна быть меньше высоты')
        if counter and self.counterbore <= self.bore:
            raise ValueError('Диаметр расточки должен быть больше сквозного отверстия')
        hole_radius = self.bore/(math.sqrt(3) if self.bore_shape == 'hex' else 2)
        maxhole = max(hole_radius, self.counterbore/2 if counter else 0)
        wall = rf*scale-maxhole
        if self.kind not in ('internal','rack') and wall < 0.15:
            raise ValueError('Отверстие пересекает зубья или оставляет стенку тоньше 0,15 мм')
        if self.bore_shape == 'd' and self.bore and not 0 < self.flat < self.bore/2:
            raise ValueError('Глубина лыски должна быть больше нуля и меньше радиуса отверстия')
        if self.kind == 'rack' and self.rim < 0.5:
            raise ValueError('Основание рейки должно быть не менее 0,5 мм')
        warnings = []
        if self.kind not in ('internal','rack','worm') and self.teeth < 2/(math.sin(math.radians(self.pressure))**2)*c**3:
            warnings.append('Мало зубьев: подрезание не моделируется. Проверьте зацепление с ответной деталью.')
        if self.kind not in ('internal','rack') and wall < 0.8:
            warnings.append('Стенка у отверстия тоньше 0,8 мм.')
        if m < 0.8:
            warnings.append('Мелкие зубья: проверьте возможности принтера и посадку пробной печатью.')
        if self.kind == 'bevel':
            warnings.append('Эскизный конический профиль: масштабированные сечения, без расчёта сопряжённой пары.')
        if self.kind == 'worm':
            warnings.append('Трапецеидальный винт. Сопряжённое червячное колесо и контакт не рассчитываются.')
        if self.kind == 'internal':
            warnings.append('Проверьте интерференцию внутренней пары; одинакового модуля недостаточно.')
        return dict(module=m, rp=rp, rb=rb, ra=ra, rf=rf, alpha=alpha, beta=beta,
                    halfbase=halfbase, scale=scale, counter=counter, wall=wall,
                    outside=2*(rf+self.rim) if self.kind=='internal' else 2*ra,
                    pitch=2*rp, root=2*rf, warnings=warnings)

def preset(teeth=48, hand='right'):
    p = Parameters(teeth=teeth, hand=hand)
    p.root_override = 5.5 + (teeth-12)*0.5619845450097661
    if teeth == 12:
        p.counterbore = p.counter_depth = p.backlash = 0
        p.hand = 'left'
    d = p.dimensions()
    p.outside = d['outside']
    return p
