import asyncio
import hashlib
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from .ai import providers
from .config import ROOT, Settings
from .db import AIRequest, Activity, Catalog, Employee, LoginSession, Recommendation, connect
from .domain.progression import candidates, trajectory
from .ingest import ImportValidationError, import_bundle
from .import_service import load_kit
from .middleware import BodyLimitMiddleware
from .schemas import DatasetBundle, DemoLogin, Selection
from .services import cache_key, employee_view, hr_overview, snapshot

API = '/api/v1'


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lifespan(app):
        engine, sessions = connect(settings.database_url)
        app.state.sessions = sessions
        app.state.settings = settings
        with sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            if settings.demo_mode and db.get(Catalog, 1) is None:
                import_bundle(db, DatasetBundle.model_validate_json((ROOT / 'examples/demo.json').read_text(encoding='utf-8')))
        yield
        engine.dispose()

    app = FastAPI(title='Career Quest', version='0.1.0', lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(OperationalError)
    async def database_busy(request, exc):
        # Never send SQL, bound parameters or filesystem paths to the browser.
        return JSONResponse({'detail': 'База данных временно недоступна. Повторите запрос.'}, 503, headers={'Retry-After': '1'})

    @app.middleware('http')
    async def protect_mutations(request: Request, call_next):
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            if request.headers.get('x-requested-with') != 'CareerQuest':
                return JSONResponse({'detail': 'Требуется заголовок X-Requested-With: CareerQuest'}, 403)
            origin = request.headers.get('origin')
            if origin and origin not in settings.allowed_origins:
                return JSONResponse({'detail': 'Недопустимый Origin'}, 403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith(API):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def user(request: Request):
        token = request.cookies.get('cq_session', '')
        digest = hashlib.sha256(token.encode()).hexdigest()
        with app.state.sessions() as db:
            row = db.get(LoginSession, digest)
            if not row or row.expires_at <= time.time():
                raise HTTPException(401, 'Войдите в приложение')
            return {'role': row.role, 'employee_id': row.employee_id}

    def hr(account=Depends(user)):
        if account['role'] != 'hr':
            raise HTTPException(403, 'Доступ разрешён только HR')
        return account

    def authorize(account, employee_id, allow_hr=True):
        if account['employee_id'] != employee_id and not (allow_hr and account['role'] == 'hr'):
            raise HTTPException(403, 'Нет доступа к этому профилю')

    @app.get(f'{API}/health')
    def health():
        with app.state.sessions() as db:
            db.execute(text('SELECT 1'))
        return {'status': 'ok', 'demo_mode': settings.demo_mode, 'ai_provider': settings.provider}

    @app.get(f'{API}/auth/demo-accounts')
    def demo_accounts():
        if not settings.demo_mode:
            return {'enabled': False, 'accounts': []}
        with app.state.sessions() as db:
            accounts = [{'id': e.id, 'label': e.profile['name'], 'role': 'employee'} for e in db.scalars(select(Employee).order_by(Employee.id))]
        return {'enabled': True, 'accounts': [*accounts, {'id': 'hr', 'label': 'HR-специалист', 'role': 'hr'}]}

    @app.post(f'{API}/auth/demo')
    def login(body: DemoLogin, response: Response, request: Request):
        if not settings.demo_mode:
            raise HTTPException(403, 'Демонстрационный вход отключён; подключите корпоративную авторизацию')
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            subject = f'login:{request.client.host if request.client else "local"}'
            attempts = db.scalar(select(func.count()).select_from(AIRequest).where(AIRequest.subject == subject, AIRequest.created_at > time.time() - 60))
            if attempts >= 20:
                raise HTTPException(429, 'Слишком много попыток входа')
            db.add(AIRequest(subject=subject, created_at=time.time(), provider='login'))
            if body.account != 'hr' and db.get(Employee, body.account) is None:
                db.commit()
                raise HTTPException(404, 'Демонстрационный аккаунт не найден')
            old_token = hashlib.sha256(request.cookies.get('cq_session', '').encode()).hexdigest()
            previous = db.get(LoginSession, old_token)
            if previous:
                db.delete(previous)
            token = secrets.token_urlsafe(32)
            account = {'role': 'hr' if body.account == 'hr' else 'employee', 'employee_id': None if body.account == 'hr' else body.account}
            db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=time.time() + 28800, **account))
            db.commit()
        response.set_cookie('cq_session', token, httponly=True, secure=settings.cookie_secure, samesite='strict', max_age=28800)
        return account

    @app.get(f'{API}/auth/me')
    def me(account=Depends(user)):
        return account

    @app.post(f'{API}/auth/logout')
    def logout(request: Request, response: Response, account=Depends(user)):
        with app.state.sessions() as db:
            row = db.get(LoginSession, hashlib.sha256(request.cookies.get('cq_session', '').encode()).hexdigest())
            if row:
                db.delete(row)
                db.commit()
        response.delete_cookie('cq_session')
        return {'ok': True}

    @app.get(f'{API}/employees')
    def employees(account=Depends(hr)):
        with app.state.sessions() as db:
            return [e.profile for e in db.scalars(select(Employee).order_by(Employee.id))]

    @app.get(f'{API}/employees/{{employee_id}}')
    def profile(employee_id: str, account=Depends(user)):
        authorize(account, employee_id)
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN')
            view = employee_view(db, employee_id)
            employee, catalog, history = snapshot(db, employee_id)
            cached = db.get(Recommendation, cache_key(employee, catalog, history, settings))
            ttl = 30 if cached and cached.payload.get('mode') == 'fallback' else 3600
            view['recommendation'] = {**cached.payload, 'cached': True} if cached and cached.created_at > time.time() - ttl else None
            return view

    @app.post(f'{API}/employees/{{employee_id}}/recommendations')
    async def recommend(employee_id: str, account=Depends(user)):
        authorize(account, employee_id)
        started = time.monotonic()
        lock = locks.setdefault(employee_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, 'Рекомендация уже рассчитывается')
        async with lock:
            with app.state.sessions() as db:
                db.connection().exec_driver_sql('BEGIN')
                employee, catalog, history = snapshot(db, employee_id)
                key = cache_key(employee, catalog, history, settings)
                cached = db.get(Recommendation, key)
                ttl = 30 if cached and cached.payload.get('mode') == 'fallback' else 3600
                if cached and cached.created_at > time.time() - ttl:
                    return {**cached.payload, 'cached': True}
                options = candidates(employee, catalog, history)
            mode = 'rules' if settings.provider == 'rules' else 'ai'
            reason, model = None, None
            selected = [c['id'] for c in options[:3]]
            if not options:
                mode, reason = 'no_candidates', 'Нет подходящей активности. Проверьте требования грейда, данные навыков и каталог.'
            elif settings.provider != 'rules' and not settings.cloud_data_approved:
                mode, reason = 'fallback', 'Передача данных в облачный AI не разрешена в настройках. Показан подбор по правилам.'
            elif settings.provider != 'rules':
                with app.state.sessions() as db:
                    # Reserve quota atomically across processes and profiles.
                    db.connection().exec_driver_sql('PRAGMA busy_timeout=250')
                    db.connection().exec_driver_sql('BEGIN IMMEDIATE')
                    now = time.time()
                    recent = db.scalar(select(func.count()).select_from(AIRequest).where(AIRequest.subject == employee_id, AIRequest.created_at > now - 60, AIRequest.provider != 'login'))
                    daily = db.scalar(select(func.count()).select_from(AIRequest).where(AIRequest.created_at > now - 86400, AIRequest.provider != 'login'))
                    if recent >= settings.per_minute or daily >= settings.per_day:
                        raise HTTPException(429, 'Лимит AI-запросов достигнут; попробуйте позже')
                    db.add(AIRequest(subject=employee_id, created_at=now, provider=settings.provider))
                    db.commit()
                context = {'profile': {k: employee[k] for k in ('role', 'grade', 'tenure_months', 'skills')}, 'trajectory': trajectory(employee, catalog), 'candidates': [{k: c[k] for k in ('id', 'title', 'type', 'format', 'changes', 'evidence', 'score', 'critical_benefit', 'session_date') if k in c} for c in options]}
                try:
                    remaining = min(settings.timeout, 8.0, 9.0 - (time.monotonic() - started))
                    if remaining <= 0:
                        raise TimeoutError('request_deadline')
                    # Independent request-level deadline also bounds alternative adapters.
                    async with asyncio.timeout(remaining):
                        model_ids, returned_model = await providers.select_events(settings, context)
                    checked = Selection(event_ids=model_ids).event_ids
                    if not set(checked) <= {item['id'] for item in options}:
                        raise ValueError('invalid_selection')
                    selected, model = checked, returned_model
                except Exception:
                    # No provider exception text: it may contain request data or credentials.
                    mode, reason = 'fallback', 'AI недоступен или ответ не прошёл проверку. Показан подбор по правилам.'
            by_id = {c['id']: c for c in options}
            result = {'items': [by_id[id_] for id_ in selected], 'mode': mode, 'provider': settings.provider if mode == 'ai' else None, 'model': model, 'reason': reason, 'cached': False, 'created_at': time.time(), 'elapsed_ms': round((time.monotonic() - started) * 1000)}
            with app.state.sessions() as db:
                db.connection().exec_driver_sql('PRAGMA busy_timeout=250')
                db.connection().exec_driver_sql('BEGIN IMMEDIATE')
                current = snapshot(db, employee_id)
                if cache_key(*current, settings) != key:
                    raise HTTPException(409, 'Профиль изменился. Повторите запрос рекомендации.')
                db.merge(Recommendation(key=key, employee_id=employee_id, payload=result, created_at=time.time()))
                db.commit()
            return result

    @app.post(f'{API}/employees/{{employee_id}}/events/{{event_id}}/complete')
    def complete(employee_id: str, event_id: str, body: dict | None = Body(default=None), account=Depends(user)):
        authorize(account, employee_id, allow_hr=False)
        if body is not None and (set(body) - {'occurrence_id'} or not isinstance(body.get('occurrence_id'), str)):
            raise HTTPException(422, 'Ожидается объект с occurrence_id в формате YYYY-MM-DD')
        occurrence_id = body.get('occurrence_id') if body else None
        if occurrence_id is not None:
            try:
                if date.fromisoformat(occurrence_id).isoformat() != occurrence_id:
                    raise ValueError
            except ValueError:
                raise HTTPException(422, 'Некорректная дата occurrence_id')
        with app.state.sessions() as db:
            # Serializes read/check/write even when two requests complete concurrently.
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            employee, catalog, history = snapshot(db, employee_id)
            source_event = next((e for e in catalog['events'] if e['id'] == event_id), None)
            repeatable = source_event and source_event.get('source_format') == 'kit-v1' and source_event.get('repeatable', False)
            if repeatable and occurrence_id is None:
                raise HTTPException(422, 'Для повторяемого события передайте occurrence_id из рекомендации')
            if any(h['event_id'] == event_id and h['status'] == 'completed'
                   and (not repeatable or h['occurred_at'] == occurrence_id) for h in history):
                return {'already_completed': True, 'profile': employee_view(db, employee_id)}
            event = next((c for c in candidates(employee, catalog, history) if c['id'] == event_id), None)
            if not event:
                raise HTTPException(422, 'Активность недоступна или не закрывает разрыв навыков')
            if occurrence_id is not None and occurrence_id != event.get('occurrence_id'):
                raise HTTPException(422, 'Указанная сессия недоступна; обновите рекомендации')
            levels = {**employee['skills']}
            for skill_id, change in event['changes'].items():
                levels[skill_id] = change['after']
            row = db.get(Employee, employee_id)
            row.profile = {**employee, 'skills': levels}
            row.revision += 1
            completed_date = event.get('session_date') or employee.get('snapshot_date') or date.today().isoformat()
            db.add(Activity(id=f'completion_{secrets.token_hex(12)}', employee_id=employee_id, event_id=event_id, status='completed', occurred_at=completed_date, changes=event['changes']))
            db.commit()
            return {'already_completed': False, 'profile': employee_view(db, employee_id)}

    @app.get(f'{API}/hr/overview')
    def overview(account=Depends(hr)):
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN')
            return hr_overview(db)

    @app.post(f'{API}/imports')
    def imports(bundle: DatasetBundle, dry_run: bool = False, account=Depends(hr)):
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            try:
                return import_bundle(db, bundle, dry_run=dry_run)
            except ImportValidationError as exc:
                return JSONResponse({'detail': str(exc), 'errors': [exc.as_dict()]}, status_code=422)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @app.post(f'{API}/imports/kit', openapi_extra={
        'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': {
            'type': 'object', 'required': ['files'],
            'properties': {'files': {'type': 'array', 'minItems': 1, 'maxItems': 4,
                                     'items': {'type': 'string', 'format': 'binary'}}},
        }}}},
    })
    async def imports_kit(request: Request, dry_run: bool = False, replace_demo: bool = False, account=Depends(hr)):
        if not request.headers.get('content-type', '').lower().startswith('multipart/form-data'):
            raise HTTPException(415, 'Загрузите исходные файлы как multipart/form-data')
        files = {}
        allowed = {'employees.json', 'events.json', 'skills.json', 'activity_history.csv'}
        async with request.form(max_files=4, max_fields=0) as form:
            for _, upload in form.multi_items():
                if not isinstance(upload, UploadFile) or upload.filename not in allowed:
                    raise HTTPException(422, 'Допустимы только employees.json, events.json, skills.json, activity_history.csv')
                if upload.filename in files:
                    raise HTTPException(422, f'Файл {upload.filename} передан повторно')
                files[upload.filename] = await upload.read()
        def apply_import():
            with app.state.sessions() as db:
                return load_kit(db, files, dry_run=dry_run, replace_demo=replace_demo)
        try:
            return await run_in_threadpool(apply_import)
        except ImportValidationError as exc:
            return JSONResponse({'detail': str(exc), 'errors': [exc.as_dict()]}, status_code=422)

    dist = ROOT / 'web/dist'
    if (dist / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/', include_in_schema=False)
    def home():
        if (dist / 'index.html').exists():
            return FileResponse(dist / 'index.html')
        return {'message': 'Запустите frontend: cd web && npm run dev', 'api_docs': '/docs'}

    return app


app = create_app()
