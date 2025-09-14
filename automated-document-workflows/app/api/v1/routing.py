"""
Routing and rule management API endpoints.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Rule, Route
from app.schemas.routing import (
    RoutingRule,
    RoutingRuleCreate,
    RoutingRuleUpdate,
    RoutingRuleResponse,
    RoutingTestRequest,
    RoutingTestResponse,
    RoutingStats,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/rules", response_model=List[RoutingRuleResponse])
async def list_rules(
    enabled_only: bool = Query(True, description="Show only enabled rules"),
    db: Session = Depends(get_db),
):
    """List routing rules."""
    
    query = db.query(Rule)
    
    if enabled_only:
        query = query.filter(Rule.enabled == True)
    
    rules = query.order_by(Rule.priority.desc(), Rule.name).all()
    
    return [RoutingRuleResponse.from_orm(rule) for rule in rules]


@router.post("/rules", response_model=RoutingRuleResponse)
async def create_rule(
    rule_data: RoutingRuleCreate,
    db: Session = Depends(get_db),
):
    """Create a new routing rule."""
    
    # Check for duplicate name
    existing = db.query(Rule).filter(Rule.name == rule_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Rule name already exists")
    
    try:
        rule = Rule(
            name=rule_data.name,
            description=rule_data.description,
            conditions=rule_data.conditions,
            actions=rule_data.actions,
            priority=rule_data.priority,
            enabled=rule_data.enabled,
        )
        
        db.add(rule)
        db.commit()
        db.refresh(rule)
        
        logger.info(f"Created routing rule: {rule.name}")
        
        return RoutingRuleResponse.from_orm(rule)
        
    except Exception as e:
        logger.error(f"Failed to create rule: {e}")
        raise HTTPException(status_code=500, detail=f"Rule creation failed: {str(e)}")


@router.get("/rules/{rule_id}", response_model=RoutingRuleResponse)
async def get_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
):
    """Get rule details by ID."""
    
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    return RoutingRuleResponse.from_orm(rule)


@router.patch("/rules/{rule_id}", response_model=RoutingRuleResponse)
async def update_rule(
    rule_id: UUID,
    update_data: RoutingRuleUpdate,
    db: Session = Depends(get_db),
):
    """Update a routing rule."""
    
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(rule, field, value)
    
    db.commit()
    db.refresh(rule)
    
    logger.info(f"Updated routing rule: {rule.name}")
    
    return RoutingRuleResponse.from_orm(rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
):
    """Delete a routing rule."""
    
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    try:
        db.delete(rule)
        db.commit()
        
        logger.info(f"Deleted routing rule: {rule.name}")
        
        return {"message": "Rule deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.post("/test", response_model=RoutingTestResponse)
async def test_routing(
    request: RoutingTestRequest,
    db: Session = Depends(get_db),
):
    """Test routing rules against sample input."""
    
    # TODO: Implement routing rule testing
    # This would load rules and test them against the provided input
    
    return RoutingTestResponse(
        test_input=request,
        results=[],
        total_rules=0,
        matched_rules=0,
        execution_time_ms=0.0,
    )


@router.get("/stats", response_model=RoutingStats)
async def get_routing_stats(
    db: Session = Depends(get_db),
):
    """Get routing system statistics."""
    
    try:
        total_rules = db.query(Rule).count()
        active_rules = db.query(Rule).filter(Rule.enabled == True).count()
        total_routes = db.query(Route).count()
        successful_routes = db.query(Route).filter(Route.applied == True).count()
        failed_routes = db.query(Route).filter(Route.applied == False, Route.error_message.isnot(None)).count()
        
        # Routes by rule
        rule_query = db.query(Route.rule_name, db.func.count(Route.id)).group_by(Route.rule_name).all()
        by_rule = {rule_name: count for rule_name, count in rule_query}
        
        # Routes by destination
        dest_query = db.query(Route.destination, db.func.count(Route.id)).group_by(Route.destination).all()
        by_destination = {dest: count for dest, count in dest_query}
        
        return RoutingStats(
            total_rules=total_rules,
            active_rules=active_rules,
            total_routes=total_routes,
            successful_routes=successful_routes,
            failed_routes=failed_routes,
            by_rule=by_rule,
            by_destination=by_destination,
            average_processing_time_ms=0.0,  # TODO: Calculate from route processing times
        )
        
    except Exception as e:
        logger.error(f"Failed to get routing stats: {e}")
        raise HTTPException(status_code=500, detail="Stats generation failed")