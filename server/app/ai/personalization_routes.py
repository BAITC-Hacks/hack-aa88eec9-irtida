"""Authenticated optional NVIDIA practice suggestions for an employee's current path."""

import asyncio
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select

if __package__.startswith('server.'):
    from server.nvidia_career_ai import NvidiaAPIError, NvidiaCareerAI, NvidiaSettings, PersonalizationError
else:
    from nvidia_career_ai import NvidiaAPIError, NvidiaCareerAI, NvidiaSettings, PersonalizationError

from ..auth import STAFF_ROLES
from ..db import AIRequest
from ..services import cache_key, snapshot
from .personalization_adapter import prepare_personalization


def install_personalization_routes(app, settings, user):
    locks: dict[str, asyncio.Lock] = {}

    @app.post('/api/v1/employees/{employee_id}/personalization')
    async def personalize(employee_id: str, request: Request, account=Depends(user)):
        if account['role'] not in STAFF_ROLES or account['employee_id'] != employee_id:
            raise HTTPException(403, 'Нет доступа к этому профилю')
        if await request.body():
            raise HTTPException(422, 'Персонализация использует текущий профиль на сервере; тело запроса не требуется')
        if not settings.nvidia_ai_mock:
            if settings.provider != 'nvidia':
                raise HTTPException(503, 'Персонализация NVIDIA не включена')
            if not settings.cloud_data_approved:
                raise HTTPException(403, 'Передача данных в облачный AI не разрешена в настройках')
            if not settings.nvidia_key:
                raise HTTPException(503, 'NVIDIA_API_KEY не настроен на сервере')

        lock = locks.setdefault(employee_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, 'Персонализация уже выполняется')
        async with lock:
            with app.state.sessions() as db:
                db.connection().exec_driver_sql('BEGIN')
                employee, catalog, history = snapshot(db, employee_id)
                version = cache_key(employee, catalog, history, settings)
            try:
                provider, context, allowed = prepare_personalization(employee, catalog, history)
                nvidia_settings = NvidiaSettings(api_key=settings.nvidia_key, model=settings.nvidia_model,
                                                 mock=settings.nvidia_ai_mock,
                                                 timeout_seconds=settings.nvidia_timeout_seconds,
                                                 max_tokens=settings.nvidia_max_tokens)
                if not settings.nvidia_ai_mock and allowed:
                    with app.state.sessions() as db:
                        db.connection().exec_driver_sql('PRAGMA busy_timeout=250')
                        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
                        now = time.time()
                        recent = db.scalar(select(func.count()).select_from(AIRequest).where(
                            AIRequest.subject == employee_id, AIRequest.created_at > now - 60,
                            AIRequest.provider != 'login'))
                        daily = db.scalar(select(func.count()).select_from(AIRequest).where(
                            AIRequest.created_at > now - 86400, AIRequest.provider != 'login'))
                        if recent >= settings.per_minute or daily >= settings.per_day:
                            raise HTTPException(429, 'Лимит AI-запросов достигнут; попробуйте позже')
                        db.add(AIRequest(subject=employee_id, created_at=now, provider='nvidia-personalization'))
                        db.commit()
                service = NvidiaCareerAI(provider, nvidia_settings)
                async with asyncio.timeout(settings.nvidia_timeout_seconds + 0.1):
                    result = await service.generate_career_personalization(context)
                if any(quest.source_event_id not in allowed for quest in result.recommended_quests):
                    raise PersonalizationError('invalid_ai_response')
                with app.state.sessions() as db:
                    current = snapshot(db, employee_id)
                    if cache_key(*current, settings) != version:
                        raise HTTPException(409, 'Профиль изменился. Повторите персонализацию.')
                return result.model_dump(mode='json', by_alias=True)
            except HTTPException:
                raise
            except PersonalizationError as exc:
                status = 502 if exc.code == 'invalid_ai_response' else 422
                raise HTTPException(status, exc.code) from None
            except NvidiaAPIError as exc:
                status = 429 if exc.code == 'rate_limited' else 503 if exc.code in {
                    'missing_key', 'timeout', 'network', 'unavailable', 'pending'} else 502
                raise HTTPException(status, exc.code) from None
            except TimeoutError:
                raise HTTPException(503, 'timeout') from None
