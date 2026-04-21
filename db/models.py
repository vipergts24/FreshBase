from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship
import datetime

Base = declarative_base()

class Intent(Base):
    """
    An Intent represents the human-readable 'Goal' that an Agent is tasked with.
    Unlike standard git commits which are textual, FreshBase tracks the semantic goal.
    """
    __tablename__ = 'intents'
    
    id = Column(Integer, primary_key=True)
    description = Column(String, nullable=False)
    status = Column(String, default="PENDING") # PENDING, IN_PROGRESS, RESOLVED, REVERTED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    commits = relationship("FreshCommit", back_populates="intent")
    runs = relationship("Run", back_populates="intent")

class FreshCommit(Base):
    """
    Links a standard Git SHA to the high-level Intent it attempted to satisfy.
    """
    __tablename__ = 'fresh_commits'
    
    id = Column(Integer, primary_key=True)
    intent_id = Column(Integer, ForeignKey('intents.id'))
    git_sha = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True) # Used to check if this was semantically reverted
    
    intent = relationship("Intent", back_populates="commits")

class Run(Base):
    """
    Tracks an agent's 'Shadow Branch' attempt to satisfy an intent.
    Records failures so agents don't make the same mistake twice.
    """
    __tablename__ = 'runs'
    
    id = Column(Integer, primary_key=True)
    intent_id = Column(Integer, ForeignKey('intents.id'))
    branch_name = Column(String, nullable=False)
    tests_passed = Column(Boolean, default=False)
    logs = Column(String) # Raw stdout/stderr from pytest
    
    intent = relationship("Intent", back_populates="runs")
