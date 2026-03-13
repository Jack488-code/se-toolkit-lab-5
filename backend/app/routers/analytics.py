"""Router for analytics endpoints.

Each endpoint performs SQL aggregation queries on the interaction data
populated by the ETL pipeline. All endpoints require a `lab` query
parameter to filter results by lab (e.g., "lab-01").
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case, distinct
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.item import ItemRecord
from app.models.learner import Learner
from app.models.interaction import InteractionLog

router = APIRouter()


class ScoreBucket(SQLModel):
    """Score bucket with count."""
    bucket: str
    count: int


class PassRate(SQLModel):
    """Pass rate for a task."""
    task: str
    avg_score: float
    attempts: int


class TimelineEntry(SQLModel):
    """Timeline entry."""
    date: str
    submissions: int


class GroupStats(SQLModel):
    """Group statistics."""
    group: str
    avg_score: float
    students: int


@router.get("/scores", response_model=list[ScoreBucket])
async def get_scores(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Score distribution histogram for a given lab.

    - Find the lab item by matching title (e.g. "lab-04" → title contains "Lab 04")
    - Find all tasks that belong to this lab (parent_id = lab.id)
    - Query interactions for these items that have a score
    - Group scores into buckets: "0-25", "26-50", "51-75", "76-100"
      using CASE WHEN expressions
    - Return a JSON array:
      [{"bucket": "0-25", "count": 12}, {"bucket": "26-50", "count": 8}, ...]
    - Always return all four buckets, even if count is 0
    """
    # Convert lab-04 to Lab 04 pattern for title matching
    lab_number = lab.replace("lab-", "Lab ")
    
    # Find the lab item
    lab_query = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.like(f"%{lab_number}%")
    )
    lab_result = await session.exec(lab_query)
    lab_item = lab_result.first()
    
    if not lab_item:
        return [
            ScoreBucket(bucket="0-25", count=0),
            ScoreBucket(bucket="26-50", count=0),
            ScoreBucket(bucket="51-75", count=0),
            ScoreBucket(bucket="76-100", count=0),
        ]
    
    # Find all task items for this lab
    task_query = select(ItemRecord.id).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    )
    task_result = await session.exec(task_query)
    task_ids = [r for r in task_result.all()]
    
    if not task_ids:
        return [
            ScoreBucket(bucket="0-25", count=0),
            ScoreBucket(bucket="26-50", count=0),
            ScoreBucket(bucket="51-75", count=0),
            ScoreBucket(bucket="76-100", count=0),
        ]
    
    # Query interactions with scores for these tasks
    # Use CASE WHEN to bucket scores
    bucket_expr = case(
        (InteractionLog.score <= 25, "0-25"),
        (InteractionLog.score <= 50, "26-50"),
        (InteractionLog.score <= 75, "51-75"),
        (InteractionLog.score <= 100, "76-100"),
        else_="0-25"
    ).label("bucket")
    
    score_query = select(
        bucket_expr,
        func.count(InteractionLog.id).label("count")
    ).where(
        InteractionLog.item_id.in_(task_ids),
        InteractionLog.score.isnot(None)
    ).group_by(bucket_expr)
    
    result = await session.exec(score_query)
    rows = result.all()
    
    # Build result with all buckets
    bucket_counts = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for row in rows:
        bucket_counts[row[0]] = row[1]
    
    return [
        ScoreBucket(bucket="0-25", count=bucket_counts["0-25"]),
        ScoreBucket(bucket="26-50", count=bucket_counts["26-50"]),
        ScoreBucket(bucket="51-75", count=bucket_counts["51-75"]),
        ScoreBucket(bucket="76-100", count=bucket_counts["76-100"]),
    ]


@router.get("/pass-rates", response_model=list[PassRate])
async def get_pass_rates(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Per-task pass rates for a given lab.

    - Find the lab item and its child task items
    - For each task, compute:
      - avg_score: average of interaction scores (round to 1 decimal)
      - attempts: total number of interactions
    - Return a JSON array:
      [{"task": "Repository Setup", "avg_score": 92.3, "attempts": 150}, ...]
    - Order by task title
    """
    # Convert lab-04 to Lab 04 pattern for title matching
    lab_number = lab.replace("lab-", "Lab ")
    
    # Find the lab item
    lab_query = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.like(f"%{lab_number}%")
    )
    lab_result = await session.exec(lab_query)
    lab_item = lab_result.first()
    
    if not lab_item:
        return []
    
    # Find all task items for this lab
    task_query = select(ItemRecord).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    ).order_by(ItemRecord.title)
    
    task_result = await session.exec(task_query)
    tasks = task_result.all()
    
    result = []
    for task in tasks:
        # Compute avg_score and attempts for this task
        stats_query = select(
            func.round(func.avg(InteractionLog.score), 1).label("avg_score"),
            func.count(InteractionLog.id).label("attempts")
        ).where(
            InteractionLog.item_id == task.id
        )
        
        stats_result = await session.exec(stats_query)
        stats = stats_result.first()
        
        avg_score = float(stats[0]) if stats[0] is not None else 0.0
        attempts = stats[1] if stats[1] is not None else 0
        
        result.append(PassRate(
            task=task.title,
            avg_score=avg_score,
            attempts=attempts
        ))
    
    return result


@router.get("/timeline", response_model=list[TimelineEntry])
async def get_timeline(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Submissions per day for a given lab.

    - Find the lab item and its child task items
    - Group interactions by date (use func.date(created_at))
    - Count the number of submissions per day
    - Return a JSON array:
      [{"date": "2026-02-28", "submissions": 45}, ...]
    - Order by date ascending
    """
    # Convert lab-04 to Lab 04 pattern for title matching
    lab_number = lab.replace("lab-", "Lab ")
    
    # Find the lab item
    lab_query = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.like(f"%{lab_number}%")
    )
    lab_result = await session.exec(lab_query)
    lab_item = lab_result.first()
    
    if not lab_item:
        return []
    
    # Find all task items for this lab
    task_query = select(ItemRecord.id).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    )
    task_result = await session.exec(task_query)
    task_ids = [r for r in task_result.all()]
    
    if not task_ids:
        return []
    
    # Group interactions by date
    timeline_query = select(
        func.date(InteractionLog.created_at).label("date"),
        func.count(InteractionLog.id).label("submissions")
    ).where(
        InteractionLog.item_id.in_(task_ids)
    ).group_by(
        func.date(InteractionLog.created_at)
    ).order_by(
        func.date(InteractionLog.created_at)
    )
    
    result = await session.exec(timeline_query)
    
    return [
        TimelineEntry(date=str(row[0]), submissions=row[1])
        for row in result.all()
    ]


@router.get("/groups", response_model=list[GroupStats])
async def get_groups(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Per-group performance for a given lab.

    - Find the lab item and its child task items
    - Join interactions with learners to get student_group
    - For each group, compute:
      - avg_score: average score (round to 1 decimal)
      - students: count of distinct learners
    - Return a JSON array:
      [{"group": "B23-CS-01", "avg_score": 78.5, "students": 25}, ...]
    - Order by group name
    """
    # Convert lab-04 to Lab 04 pattern for title matching
    lab_number = lab.replace("lab-", "Lab ")
    
    # Find the lab item
    lab_query = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.like(f"%{lab_number}%")
    )
    lab_result = await session.exec(lab_query)
    lab_item = lab_result.first()
    
    if not lab_item:
        return []
    
    # Find all task items for this lab
    task_query = select(ItemRecord.id).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    )
    task_result = await session.exec(task_query)
    task_ids = [r for r in task_result.all()]
    
    if not task_ids:
        return []
    
    # Join interactions with learners and group by student_group
    groups_query = select(
        Learner.student_group.label("group"),
        func.round(func.avg(InteractionLog.score), 1).label("avg_score"),
        func.count(distinct(InteractionLog.learner_id)).label("students")
    ).join(
        Learner, InteractionLog.learner_id == Learner.id
    ).where(
        InteractionLog.item_id.in_(task_ids)
    ).group_by(
        Learner.student_group
    ).order_by(
        Learner.student_group
    )
    
    result = await session.exec(groups_query)
    
    return [
        GroupStats(
            group=row[0],
            avg_score=float(row[1]) if row[1] is not None else 0.0,
            students=row[2] if row[2] is not None else 0
        )
        for row in result.all()
    ]
