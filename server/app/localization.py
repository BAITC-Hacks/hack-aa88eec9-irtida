"""Presentation-only translations. IDs, roles used for eligibility and DB stay canonical."""
import json
import math
import re

# English catalog labels -> Russian / Kazakh. No employee records are embedded.
LABELS = {
    'Backend Engineer': ('Backend-разработчик', 'Backend әзірлеуші'),
    'Frontend Engineer': ('Frontend-разработчик', 'Frontend әзірлеуші'),
    'Data Analyst': ('Аналитик данных', 'Деректер талдаушысы'),
    'QA Engineer': ('Инженер по качеству', 'Сапа инженері'),
    'Product Manager': ('Менеджер продукта', 'Өнім менеджері'),
    'HR Business Partner': ('HR бизнес-партнёр', 'HR бизнес-серіктесі'),
    'Sales Manager': ('Менеджер по продажам', 'Сату менеджері'),
    'Customer Support Specialist': ('Специалист поддержки клиентов', 'Клиенттерді қолдау маманы'),
    'API Design': ('Проектирование API', 'API жобалау'),
    'System Design': ('Проектирование систем', 'Жүйелерді жобалау'),
    'Cloud Platforms': ('Облачные платформы', 'Бұлттық платформалар'),
    'Containers & Orchestration': ('Контейнеры и оркестрация', 'Контейнерлер және оркестрация'),
    'Application Security': ('Безопасность приложений', 'Қолданбалар қауіпсіздігі'),
    'Observability': ('Наблюдаемость систем', 'Жүйелерді бақылау'),
    'Web Performance': ('Производительность веб-приложений', 'Веб өнімділігі'),
    'Web Accessibility': ('Доступность веб-интерфейсов', 'Веб қолжетімділігі'),
    'Test Design': ('Проектирование тестов', 'Тестілерді жобалау'),
    'Test Automation': ('Автоматизация тестирования', 'Тестілеуді автоматтандыру'),
    'API Testing': ('Тестирование API', 'API тестілеу'),
    'Load Testing': ('Нагрузочное тестирование', 'Жүктемелік тестілеу'),
    'Statistics': ('Статистика', 'Статистика'),
    'A/B Testing': ('A/B-тестирование', 'A/B тестілеу'),
    'Data Visualization': ('Визуализация данных', 'Деректерді визуализациялау'),
    'BI Tools': ('Инструменты BI', 'BI құралдары'),
    'Data Modeling': ('Моделирование данных', 'Деректерді модельдеу'),
    'Machine Learning Fundamentals': ('Основы машинного обучения', 'Машиналық оқыту негіздері'),
    'Product Discovery': ('Исследование продукта', 'Өнімді зерттеу'),
    'Roadmapping & Prioritization': ('Дорожная карта и приоритеты', 'Жол картасы және басымдықтар'),
    'Product Analytics': ('Продуктовая аналитика', 'Өнім аналитикасы'),
    'UX Research': ('Исследование пользовательского опыта', 'Пайдаланушы тәжірибесін зерттеу'),
    'Requirements Writing': ('Описание требований', 'Талаптарды жазу'),
    'Agile Practices': ('Практики Agile', 'Agile тәжірибелері'),
    'Project Management': ('Управление проектами', 'Жобаларды басқару'),
    'Talent Acquisition': ('Подбор персонала', 'Персоналды іріктеу'),
    'Employee Relations': ('Отношения с сотрудниками', 'Қызметкерлермен қарым-қатынас'),
    'Labor Law': ('Трудовое право', 'Еңбек құқығы'),
    'HR Analytics': ('HR-аналитика', 'HR аналитикасы'),
    'Learning Program Design': ('Разработка программ обучения', 'Оқу бағдарламаларын әзірлеу'),
    'Compensation & Benefits': ('Компенсации и льготы', 'Өтемақылар мен жеңілдіктер'),
    'Prospecting': ('Поиск клиентов', 'Клиенттерді іздеу'),
    'Negotiation': ('Переговоры', 'Келіссөздер'),
    'CRM Systems': ('CRM-системы', 'CRM жүйелері'),
    'Account Management': ('Работа с клиентскими аккаунтами', 'Клиенттік шоттарды басқару'),
    'Product Knowledge': ('Знание продукта', 'Өнімді білу'),
    'Customer Service': ('Клиентский сервис', 'Клиенттерге қызмет көрсету'),
    'Technical Troubleshooting': ('Диагностика технических проблем', 'Техникалық ақауларды анықтау'),
    'Communication': ('Коммуникация', 'Қарым-қатынас'),
    'Public Speaking': ('Публичные выступления', 'Көпшілік алдында сөйлеу'),
    'Written Communication': ('Письменная коммуникация', 'Жазбаша қарым-қатынас'),
    'Stakeholder Management': ('Работа с заинтересованными сторонами', 'Мүдделі тараптармен жұмыс'),
    'Leadership': ('Лидерство', 'Көшбасшылық'),
    'Mentoring': ('Менторство', 'Тәлімгерлік'),
    'Feedback': ('Обратная связь', 'Кері байланыс'),
    'Conflict Resolution': ('Разрешение конфликтов', 'Қақтығыстарды шешу'),
    'Teamwork': ('Командная работа', 'Командалық жұмыс'),
    'Emotional Intelligence': ('Эмоциональный интеллект', 'Эмоциялық интеллект'),
    'Problem Solving': ('Решение проблем', 'Мәселелерді шешу'),
    'Critical Thinking': ('Критическое мышление', 'Сыни ойлау'),
    'Time Management': ('Управление временем', 'Уақытты басқару'),
    'Adaptability': ('Адаптивность', 'Бейімделу'),
    'Information Security Awareness': ('Основы информационной безопасности', 'Ақпараттық қауіпсіздік негіздері'),
    'Personal Data Protection': ('Защита персональных данных', 'Дербес деректерді қорғау'),
    'Code of Conduct & Workplace Safety': ('Деловая этика и безопасность труда', 'Іскерлік әдеп және еңбек қауіпсіздігі'),
    'New Employee Onboarding': ('Адаптация нового сотрудника', 'Жаңа қызметкерді бейімдеу'),
    'System Design Fundamentals': ('Основы проектирования систем', 'Жүйелерді жобалау негіздері'),
    'Designing High-Load Systems': ('Проектирование высоконагруженных систем', 'Жоғары жүктемелі жүйелерді жобалау'),
    'Architecture Review Circle': ('Клуб архитектурных разборов', 'Архитектураны талдау клубы'),
    'Business Writing & Documentation': ('Деловая переписка и документация', 'Іскерлік хат алмасу және құжаттама'),
    'Cloud Certification Prep': ('Подготовка к облачной сертификации', 'Бұлттық сертификаттауға дайындық'),
    'Kubernetes in Practice': ('Kubernetes на практике', 'Kubernetes тәжірибеде'),
    'Secure Coding Workshop': ('Практикум безопасной разработки', 'Қауіпсіз әзірлеу практикумы'),
    'Advanced Python': ('Продвинутый Python', 'Тереңдетілген Python'),
    'TypeScript in Depth': ('Углублённый TypeScript', 'Тереңдетілген TypeScript'),
    'Web Performance Deep Dive': ('Углублённая веб-производительность', 'Веб өнімділігін терең зерттеу'),
    'Web Performance Fundamentals': ('Основы веб-производительности', 'Веб өнімділігі негіздері'),
    'Accessible Interfaces': ('Доступные интерфейсы', 'Қолжетімді интерфейстер'),
    'React Patterns & State Management': ('Паттерны React и управление состоянием', 'React үлгілері және күйді басқару'),
    'Test Automation Bootcamp': ('Интенсив по автоматизации тестирования', 'Тестілеуді автоматтандыру курсы'),
    'API & Performance Testing Workshop': ('Практикум API и нагрузочного тестирования', 'API және жүктемелік тестілеу практикумы'),
    'Applied Statistics for Analysts': ('Прикладная статистика для аналитиков', 'Талдаушыларға арналған қолданбалы статистика'),
    'A/B Testing Workshop': ('Практикум A/B-тестирования', 'A/B тестілеу практикумы'),
    'SQL & BI for Analytics': ('SQL и BI для аналитики', 'Аналитикаға арналған SQL және BI'),
    'Data Storytelling & Visualization': ('Истории и визуализация данных', 'Деректерді баяндау және визуализациялау'),
    'Machine Learning for Analysts': ('Машинное обучение для аналитиков', 'Талдаушыларға арналған машиналық оқыту'),
    'Dimensional Data Modeling': ('Многомерное моделирование данных', 'Деректерді көпөлшемді модельдеу'),
    'Product Discovery Lab': ('Лаборатория исследования продукта', 'Өнімді зерттеу зертханасы'),
    'Roadmapping & Agile Planning': ('Дорожная карта и Agile-планирование', 'Жол картасы және Agile жоспарлау'),
    'Labor Law & Employee Relations': ('Трудовое право и отношения с сотрудниками', 'Еңбек құқығы және қызметкерлермен қарым-қатынас'),
    'People Analytics & Total Rewards': ('Кадровая аналитика и вознаграждения', 'Кадрлық аналитика және сыйақылар'),
    'Structured Interviewing': ('Структурированное интервью', 'Құрылымдалған сұхбат'),
    'Designing Learning Programs': ('Проектирование программ обучения', 'Оқу бағдарламаларын жобалау'),
    'Negotiation Masterclass': ('Мастер-класс по переговорам', 'Келіссөздер шеберлік сабағы'),
    'Consultative Selling & Prospecting': ('Консультативные продажи и поиск клиентов', 'Кеңес беру арқылы сату және клиент іздеу'),
    'Handling Difficult Conversations': ('Работа со сложными диалогами', 'Күрделі диалогтарды жүргізу'),
    'Technical Troubleshooting Academy': ('Академия технической диагностики', 'Техникалық диагностика академиясы'),
    'Public Speaking Club': ('Клуб публичных выступлений', 'Көпшілік алдында сөйлеу клубы'),
    'Mentor Track': ('Программа менторства', 'Тәлімгерлік бағдарламасы'),
    'Leadership Foundations': ('Основы лидерства', 'Көшбасшылық негіздері'),
    'Time & Priority Management': ('Управление временем и приоритетами', 'Уақыт пен басымдықтарды басқару'),
    'Structured Problem Solving': ('Системное решение проблем', 'Мәселелерді жүйелі шешу'),
}

def label(value, locale):
    if not isinstance(value, str):
        return value
    return LABELS.get(value, (value, value))[0 if locale == 'ru' else 1] if locale != 'en' else value


EVENT_LABELS = {
    'course': ('Курс', 'Course', 'Курс'), 'workshop': ('Практикум', 'Workshop', 'Практикум'),
    'mentoring': ('Менторство', 'Mentoring', 'Тәлімгерлік'), 'meetup': ('Встреча', 'Meetup', 'Кездесу'),
    'speaking': ('Выступления', 'Public speaking', 'Көпшілік алдында сөйлеу'),
    'speaking_club': ('Клуб выступлений', 'Speaking club', 'Шешендік клубы'),
    'certification': ('Сертификация', 'Certification', 'Сертификаттау'),
    'compliance': ('Обязательное обучение', 'Mandatory training', 'Міндетті оқу'),
    'onboarding': ('Онбординг', 'Onboarding', 'Бейімделу'),
    'training': ('Обучение', 'Training', 'Оқу'), 'project': ('Проект', 'Project', 'Жоба'),
    'assessment': ('Оценка навыков', 'Skill assessment', 'Дағдыларды бағалау'),
    'webinar': ('Вебинар', 'Webinar', 'Вебинар'),
    'online': ('Онлайн', 'Online', 'Онлайн'), 'offline': ('Очно', 'In person', 'Офлайн'),
    'self_paced': ('В своём темпе', 'Self-paced', 'Өз қарқынымен'),
}


def event_label(value, locale):
    translations = EVENT_LABELS.get(value) if isinstance(value, str) else None
    return translations[('ru', 'en', 'kk').index(locale)] if translations else value or '—'


def _evidence_text(item, locale):
    facts = item.get('facts')
    if not facts:
        return item['text']  # Old cache entries expire; never invent missing facts.
    factor = item['factor']
    if factor == 'grade':
        return f"{label(facts['role'], locale)}, {facts['grade']} → {facts['next_grade']}"
    if factor == 'skill_gap':
        return '; '.join(f"{label(s['name'], locale)}: {s['level']} → {s['required']}" for s in facts['skills'])
    if factor == 'next_level':
        b, g, c = facts['benefit'], facts['next_grade'], facts['critical']
        texts = {'ru': f'Закрывает {b} ур. разрыва для {g}. По критическим навыкам: {c}.',
                 'en': f'Closes {b} skill-gap levels towards {g}; critical skills: {c}.',
                 'kk': f'{g} деңгейіне дейінгі дағды алшақтығын {b} деңгейге азайтады. Маңызды дағдылар: {c}.'}
        return texts[locale]
    if factor == 'history':
        counts = facts['counts']
        if not counts:
            return {'ru': 'Истории участия в этом типе и формате пока нет; предпочтения неизвестны.',
                    'en': 'No participation history for this type and format; preferences are unknown.',
                    'kk': 'Бұл түр мен формат бойынша қатысу тарихы жоқ; қалаулар белгісіз.'}[locale]
        keys = ['completed', 'no_show', 'declined', 'dropped', 'in_progress', 'overdue']
        names = {'ru': ['завершено', 'неявок', 'отказов', 'прервано', 'в процессе', 'просрочено'],
                 'en': ['completed', 'no-shows', 'declined', 'dropped', 'in progress', 'overdue'],
                 'kk': ['аяқталды', 'келмеді', 'бас тартты', 'тоқтатылды', 'орындалуда', 'мерзімі өтті']}[locale]
        prefix = f"{event_label(facts['type'], locale)} / {event_label(facts['format'], locale)}: "
        if not facts['official']:
            return prefix + f"{names[0]} {counts.get('completed', 0)}, " + {'ru': 'пропусков/отказов', 'en': 'missed/declined', 'kk': 'қатыспады/бас тартты'}[locale] + f" {facts['skipped']}."
        return prefix + ', '.join(f'{name}: {counts.get(key, 0)}' for key, name in zip(keys, names)) + '.'
    return item['text']


def evidence_text(item, locale):
    # Old or malformed cached facts must not break otherwise valid responses.
    try:
        return _evidence_text(item, locale)
    except (KeyError, TypeError, ValueError, AttributeError):
        return item.get('text', '')


REASONS = {
    'Нет подходящей активности. Проверьте требования грейда, данные навыков и каталог.':
        ('No eligible activity. Review grade requirements, skills and the catalog.', 'Сәйкес белсенділік жоқ. Деңгей талаптарын, дағдыларды және каталогты тексеріңіз.'),
    'Передача данных в облачный AI не разрешена в настройках. Показан подбор по правилам.':
        ('Cloud AI processing is disabled. Showing a rules-based selection.', 'Бұлттық AI өңдеуі өшірілген. Ережелер бойынша іріктеу көрсетілді.'),
    'AI недоступен или ответ не прошёл проверку. Показан подбор по правилам.':
        ('AI is unavailable or its response failed validation. Showing a rules-based selection.', 'AI қолжетімсіз немесе жауап тексеруден өтпеді. Ережелер бойынша іріктеу көрсетілді.'),
}

ERROR_MESSAGES = {
    'Войдите в приложение': ('Sign in to continue', 'Жалғастыру үшін кіріңіз'),
    'Профиль учётной записи недоступен': ('This account profile is unavailable', 'Есептік жазба профилі қолжетімсіз'),
    'Неверные имя пользователя, пароль или роль': ('Invalid username, password or role', 'Пайдаланушы аты, құпиясөз немесе рөл қате'),
    'Учётная запись изменилась. Повторите вход': ('The account has changed. Sign in again', 'Есептік жазба өзгерді. Қайта кіріңіз'),
    'Слишком много попыток входа': ('Too many sign-in attempts', 'Кіру әрекеттері тым көп'),
    'Слишком много попыток входа. Повторите через минуту.': ('Too many sign-in attempts. Try again in one minute.', 'Кіру әрекеттері тым көп. Бір минуттан кейін қайталаңыз.'),
    'Первичная настройка уже выполнена. Войдите в существующую учётную запись': ('Initial setup is complete. Sign in with an existing account', 'Бастапқы баптау аяқталған. Қолданыстағы есептік жазбаға кіріңіз'),
    'Первичная настройка доступна только на компьютере сервера': ('Initial setup is only available on the server computer', 'Бастапқы баптау тек сервер компьютерінде қолжетімді'),
    'Приглашение недействительно, уже использовано или истекло': ('The invitation is invalid, already used or expired', 'Шақыру жарамсыз, қолданылған немесе мерзімі өткен'),
    'Выбранная роль не соответствует приглашению': ('The selected role does not match the invitation', 'Таңдалған рөл шақыруға сәйкес келмейді'),
    'Имя пользователя уже занято': ('This username is already taken', 'Бұл пайдаланушы аты бос емес'),
    'Профиль из приглашения недоступен': ('The invited employee profile is unavailable', 'Шақырудағы қызметкер профилі қолжетімсіз'),
    'Для этого сотрудника уже создана учётная запись': ('This employee already has an account', 'Бұл қызметкердің есептік жазбасы бар'),
    'Сотрудник не найден': ('Employee not found', 'Қызметкер табылмады'),
    'Доступ разрешён только HR': ('Only HR can access this resource', 'Бұл ресурс тек HR үшін қолжетімді'),
    'Нет доступа к этому профилю': ('You do not have access to this profile', 'Бұл профильге қолжетімділік жоқ'),
    'База данных временно недоступна. Повторите запрос.': ('The database is temporarily unavailable. Try again.', 'Деректер базасы уақытша қолжетімсіз. Қайталап көріңіз.'),
    'Требуется заголовок X-Requested-With: CareerQuest': ('The X-Requested-With: CareerQuest header is required', 'X-Requested-With: CareerQuest тақырыбы қажет'),
    'Недопустимый Origin': ('This request origin is not allowed', 'Бұл сұрау көзіне рұқсат берілмеген'),
    'Демонстрационный вход отключён; подключите корпоративную авторизацию': ('Demo sign-in is disabled. Use an account to sign in', 'Демо кіру өшірілген. Есептік жазба арқылы кіріңіз'),
    'Демонстрационный аккаунт не найден': ('Demo account not found', 'Демо есептік жазба табылмады'),
    'Рекомендация уже рассчитывается': ('A recommendation is already being calculated', 'Ұсыныс есептеліп жатыр'),
    'Лимит AI-запросов достигнут; попробуйте позже': ('The AI request limit has been reached. Try again later', 'AI сұрауларының шегіне жеттіңіз. Кейінірек қайталаңыз'),
    'Профиль изменился. Повторите запрос рекомендации.': ('The profile changed. Request recommendations again.', 'Профиль өзгерді. Ұсыныстарды қайта сұраңыз.'),
    'Ожидается объект с occurrence_id в формате YYYY-MM-DD': ('Expected an object with occurrence_id in YYYY-MM-DD format', 'YYYY-MM-DD пішіміндегі occurrence_id бар нысан қажет'),
    'Некорректная дата occurrence_id': ('Invalid occurrence_id date', 'occurrence_id күні жарамсыз'),
    'Для повторяемого события передайте occurrence_id из рекомендации': ('Use the occurrence_id from the recommendation for a recurring event', 'Қайталанатын іс-шара үшін ұсыныстағы occurrence_id мәнін жіберіңіз'),
    'Активность недоступна или не закрывает разрыв навыков': ('This activity is unavailable or does not close a skill gap', 'Іс-шара қолжетімсіз немесе дағды алшақтығын азайтпайды'),
    'Указанная сессия недоступна; обновите рекомендации': ('This session is unavailable. Refresh recommendations', 'Бұл сессия қолжетімсіз. Ұсыныстарды жаңартыңыз'),
    'Загрузите исходные файлы как multipart/form-data': ('Upload the original files as multipart/form-data', 'Бастапқы файлдарды multipart/form-data түрінде жүктеңіз'),
    'Допустимы только employees.json, events.json, skills.json, activity_history.csv': ('Only employees.json, events.json, skills.json and activity_history.csv are allowed', 'Тек employees.json, events.json, skills.json және activity_history.csv рұқсат етіледі'),
    'Некорректный Content-Length': ('Invalid Content-Length', 'Content-Length жарамсыз'),
    'Максимальный размер запроса — 5 МБ': ('The maximum request size is 5 MB', 'Сұраудың ең үлкен көлемі — 5 МБ'),
    'Укажите имя': ('Enter a display name', 'Көрсетілетін атты енгізіңіз'),
    'Сотруднику нужен employee_id; приглашение HR не привязывается к профилю': ('Employees require employee_id; HR invitations do not link to an employee profile', 'Қызметкерге employee_id қажет; HR шақыруы қызметкер профиліне байланыстырылмайды'),
}

VALIDATION_MESSAGES = {
    'Field required': ('Обязательное поле', 'Міндетті өріс'),
    'Extra inputs are not permitted': ('Лишние поля не допускаются', 'Артық өрістерге рұқсат жоқ'),
    'Input should be a valid string': ('Ожидается строка', 'Мәтіндік жол қажет'),
    'Input should be a valid integer': ('Ожидается целое число', 'Бүтін сан қажет'),
    "Input should be 'employee' or 'hr'": ('Ожидается роль employee или hr', 'employee немесе hr рөлі қажет'),
}


def error_text(value, locale):
    if not isinstance(value, str):
        return value
    if value in ERROR_MESSAGES:
        return value if locale == 'ru' else ERROR_MESSAGES[value][0 if locale == 'en' else 1]
    if value.startswith('Value error, '):
        return error_text(value.removeprefix('Value error, '), locale)
    if value in VALIDATION_MESSAGES:
        return value if locale == 'en' else VALIDATION_MESSAGES[value][0 if locale == 'ru' else 1]
    if match := re.fullmatch(r'String should have at (least|most) (\d+) characters', value):
        bound, count = match.groups()
        if locale == 'en':
            return value
        return (f'Минимум {count} символов' if bound == 'least' else f'Максимум {count} символов') if locale == 'ru' else (f'Кемінде {count} таңба' if bound == 'least' else f'Ең көбі {count} таңба')
    if match := re.fullmatch(r'Value should have at (least|most) (\d+) items after validation, not \d+', value):
        bound, count = match.groups()
        if locale == 'en':
            return value
        return (f'Длина должна быть не менее {count}' if bound == 'least' else f'Длина должна быть не более {count}') if locale == 'ru' else (f'Ұзындығы кемінде {count} болуы керек' if bound == 'least' else f'Ұзындығы ең көбі {count} болуы керек')
    if value.startswith('String should match pattern '):
        return {'ru': 'Значение не соответствует допустимому формату', 'en': 'Value does not match the allowed format', 'kk': 'Мән рұқсат етілген пішімге сәйкес келмейді'}[locale]
    if match := re.fullmatch(r'Файл (employees\.json|events\.json|skills\.json|activity_history\.csv) передан повторно', value):
        filename = match.group(1)
        return {'ru': value, 'en': f'File {filename} was uploaded more than once', 'kk': f'{filename} файлы бірнеше рет жүктелген'}[locale]
    return value


NO_STEP_DETAILS = {
    'Lead — высший грейд в официальном наборе; требования следующего грейда отсутствуют.': ('Lead is the highest grade in the dataset; there are no next-grade requirements.', 'Lead — деректердегі ең жоғары деңгей; келесі деңгей талаптары жоқ.'),
    'Не заданы требования следующего грейда для этой роли и текущего грейда.': ('Next-grade requirements are not defined for this role and grade.', 'Бұл рөл мен деңгей үшін келесі деңгей талаптары белгіленбеген.'),
    'В правиле следующего грейда нет положительных требований; прогресс не вычисляется.': ('Next-grade requirements contain no positive targets; progress cannot be calculated.', 'Келесі деңгейде оң мақсатты мәндер жоқ; ілгерілеу есептелмейді.'),
    'Все известные требования следующего грейда по навыкам уже выполнены.': ('All known next-grade skill requirements are already met.', 'Келесі деңгейдің барлық белгілі дағды талаптары орындалған.'),
    'Каталог активностей пуст.': ('The activity catalog is empty.', 'Іс-шаралар каталогы бос.'),
}
BLOCKERS = {
    'completed': ('already completed', 'бұрын аяқталған'), 'role': ('not eligible for this role', 'рөлге сәйкес келмейді'),
    'grade': ('not eligible for this grade', 'деңгейге сәйкес келмейді'), 'unknown_skill': ('skill levels need assessment', 'дағды деңгейлерін бағалау қажет'),
    'skill_cap': ('skill gain cap reached', 'дағды өсімінің шегіне жеткен'), 'no_relevant_gain': ('does not close next-grade gaps', 'келесі деңгей алшақтығын азайтпайды'),
    'mandatory': ('mandatory HR assignments are excluded', 'HR міндетті тапсырмалары ұсынылмайды'),
    'prerequisites': ('prerequisites are not met', 'алдын ала талаптар орындалмаған'),
    'no_upcoming_session': ('no available upcoming session', 'қолжетімді алдағы сессия жоқ'),
}


def no_step_detail(value, locale):
    original = value.get('reason_detail')
    if locale == 'ru' or not isinstance(original, str):
        return original
    index = 0 if locale == 'en' else 1
    if original in NO_STEP_DETAILS:
        return NO_STEP_DETAILS[original][index]
    if value.get('reason') == 'missing_skills':
        prefix, suffix = 'Неизвестны уровни навыков: ', '. Доступного шага по известным разрывам нет.'
        if original.startswith(prefix) and original.endswith(suffix):
            names = ', '.join(label(name, locale) for name in original[len(prefix):-len(suffix)].split(', '))
            return f'Skill levels not assessed: {names}. No available step closes known gaps.' if locale == 'en' else f'Бағаланбаған дағдылар: {names}. Белгілі алшақтықтарды азайтатын қолжетімді қадам жоқ.'
    blockers = value.get('blockers')
    if value.get('reason') == 'no_eligible_activity' and isinstance(blockers, dict) and blockers:
        details = '; '.join(f"{BLOCKERS.get(key, (key, key))[index]} — {count}" for key, count in sorted(blockers.items()) if isinstance(count, (int, float)) and not isinstance(count, bool))
        if details:
            return ('No eligible activity: ' if locale == 'en' else 'Сәйкес іс-шара жоқ: ') + details + '.'
    return original


def localize(value, locale, _kind=None):
    if isinstance(value, list):
        return [localize(item, locale, _kind) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        # Only known skill collections/changes contain translatable names.
        # Employee/account names, including names equal to a catalog label,
        # remain exactly as supplied. IDs never determine a person's display.
        child_kind = 'skill' if _kind == 'skill-map' else None
        if key in {'skill_catalog', 'skills', 'gaps'} and isinstance(item, list):
            child_kind = 'skill'
        elif key == 'changes' and isinstance(item, dict):
            child_kind = 'skill-map'
        elif key in {'events', 'available', 'items', 'history', 'participation'} and isinstance(item, list):
            child_kind = 'event'
        result[key] = localize(item, locale, child_kind)
    if _kind == 'skill' and isinstance(value.get('name'), str):
        result['name'] = label(value['name'], locale)
    if _kind == 'event' and isinstance(value.get('title'), str):
        result['title'] = label(value['title'], locale)
    if 'role' in value and isinstance(value['role'], str):
        result['role_label'] = label(value['role'], locale)
    if isinstance(value.get('events'), list) and isinstance(value.get('skills'), list):
        roles = sorted({role for event in value['events'] if isinstance(event, dict) and isinstance(event.get('roles'), list)
                        for role in event['roles'] if isinstance(role, str)})
        result['role_labels'] = {role: label(role, locale) for role in roles}
    if 'factor' in value and 'text' in value:
        result['text'] = evidence_text(value, locale)
    if locale != 'ru' and isinstance(value.get('reason'), str) and value['reason'] in REASONS:
        result['reason'] = REASONS[value['reason']][0 if locale == 'en' else 1]
    if 'reason_detail' in value:
        result['reason_detail'] = no_step_detail(value, locale)
    for key in ('detail', 'msg'):
        if isinstance(value.get(key), str):
            result[key] = error_text(value[key], locale)
    return result


def requested_locale(headers):
    language = ','.join(value.decode('latin1') for key, value in headers if key.lower() == b'accept-language')
    choices = []
    for order, part in enumerate(language.lower().split(',')):
        pieces = part.strip().split(';')
        code = pieces[0].strip().split('-')[0]
        if code not in ('ru', 'en', 'kk'):
            continue
        try:
            quality = next((float(piece.strip()[2:]) for piece in pieces[1:] if piece.strip().startswith('q=')), 1.0)
        except ValueError:
            continue
        if math.isfinite(quality) and 0 < quality <= 1:
            choices.append((quality, -order, code))
    return max(choices)[2] if choices else None


class LocalizationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        locale = requested_locale(scope.get('headers', []))
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/api/v1'):
            return await self.app(scope, receive, send)
        start, chunks = None, []

        async def translate(message):
            nonlocal start
            if message['type'] == 'http.response.start':
                if not any(k.lower() == b'content-type' and b'application/json' in v.lower() for k, v in message['headers']):
                    return await send(message)
                start = message
            elif message['type'] == 'http.response.body' and start is not None:
                chunks.append(message.get('body', b''))
                if not message.get('more_body', False):
                    raw = b''.join(chunks)
                    if locale:
                        try:
                            raw = json.dumps(localize(json.loads(raw), locale), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                        except (ValueError, TypeError, KeyError, AttributeError):
                            pass
                    headers = start['headers']
                    vary = [item.strip() for key, value in headers if key.lower() == b'vary' for item in value.decode('latin1').split(',') if item.strip()]
                    if not any(item.lower() in {'accept-language', '*'} for item in vary):
                        vary.append('Accept-Language')
                    replaced = {b'content-length', b'vary'} | ({b'content-language'} if locale else set())
                    start = {**start, 'headers': [(key, value) for key, value in headers if key.lower() not in replaced]}
                    start['headers'] += [(b'content-length', str(len(raw)).encode()), (b'vary', ', '.join(vary).encode('latin1'))]
                    if locale:
                        start['headers'].append((b'content-language', locale.encode()))
                    await send(start)
                    await send({**message, 'body': raw})
            else:
                await send(message)

        await self.app(scope, receive, translate)
