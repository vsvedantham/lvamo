import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.admin import AdminProject, AdminProjectUpdate, AdminUser, AdminUserUpdate, AuditEntry, MentorAssign
from app.prosho.services import admin
from app.prosho.services.admin import get_admin

router = APIRouter(prefix="/admin")


@router.get("/users", response_model=list[AdminUser])
async def list_users(_: ProshoUser = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    return await admin.list_users(db)


@router.patch("/users/{user_id}", response_model=list[AdminUser])
async def update_user(user_id: uuid.UUID, body: AdminUserUpdate, me: ProshoUser = Depends(get_admin),
                      db: AsyncSession = Depends(get_db)):
    await admin.update_user(user_id, body, me, db)
    return await admin.list_users(db)


@router.get("/projects", response_model=list[AdminProject])
async def list_projects(_: ProshoUser = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    return await admin.list_projects(db)


@router.patch("/projects/{project_id}", response_model=list[AdminProject])
async def update_project(project_id: uuid.UUID, body: AdminProjectUpdate, me: ProshoUser = Depends(get_admin),
                         db: AsyncSession = Depends(get_db)):
    await admin.set_project_active(project_id, body.is_active, me, db)
    return await admin.list_projects(db)


@router.post("/projects/{project_id}/mentors", response_model=list[AdminProject], status_code=status.HTTP_201_CREATED)
async def assign_mentor(project_id: uuid.UUID, body: MentorAssign, me: ProshoUser = Depends(get_admin),
                        db: AsyncSession = Depends(get_db)):
    await admin.assign_mentor(project_id, body.mentor_id, me, db)
    return await admin.list_projects(db)


@router.delete("/projects/{project_id}/mentors/{mentor_id}", response_model=list[AdminProject])
async def remove_mentor(project_id: uuid.UUID, mentor_id: uuid.UUID, me: ProshoUser = Depends(get_admin),
                        db: AsyncSession = Depends(get_db)):
    await admin.remove_mentor(project_id, mentor_id, me, db)
    return await admin.list_projects(db)


@router.get("/audit", response_model=list[AuditEntry])
async def audit_log(limit: int = Query(default=100, ge=1, le=500), before: Optional[datetime] = None,
                    _: ProshoUser = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    return await admin.audit_log(db, limit, before)
