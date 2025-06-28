from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime

class TripLegInput(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    date: str
    time: str

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%m/%d/%Y")
            return v
        except ValueError:
            raise ValueError("Date must be in MM/DD/YYYY format")

    @validator("time")
    def validate_time(cls, v):
        if not v or ":" not in v:
            raise ValueError("Time must be in HH:MM format")
        return v

class TripInput(BaseModel):
    route: str
    departure_date: str
    passenger_count: int
    budget: str
    notes: Optional[str] = ""
    planner_name: str
    planner_email: str
    partner_names: List[str]
    partner_emails: List[str]
    status: str
    legs: List[TripLegInput]

    @validator("departure_date")
    def validate_departure_date(cls, v):
        try:
            datetime.strptime(v, "%m/%d/%Y")
            return v
        except ValueError:
            raise ValueError("Departure date must be in MM/DD/YYYY format")

class QuoteInput(BaseModel):
    trip_id: str
    broker_name: str
    operator_name: str
    aircraft_type: str
    aircraft_category: str
    aircraft_year: str
    price: str
    taxes_included: bool
    wifi: bool
    yom: str
    refurbished_year: str
    notes: Optional[str] = ""
    submitted_by_email: str
    shared_with_emails: str
