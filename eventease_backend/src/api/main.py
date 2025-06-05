from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

app = FastAPI(
    title="EventEase Backend API",
    description=(
        "Backend API for creating and managing events, invitations, RSVPs, "
        "calendar, and notifications."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------- Models ---------


class RSVPStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class NotificationType(str, Enum):
    reminder = "reminder"
    update = "update"


class Invitation(BaseModel):
    id: int
    event_id: int
    invitee_email: str
    status: RSVPStatus = RSVPStatus.pending


class Event(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    date: datetime
    location: str
    created_by: str
    invitees: List[str]


class EventCreateRequest(BaseModel):
    title: str = Field(..., example="Team Meeting")
    description: Optional[str] = Field(None, example="Discuss quarterly goals")
    date: datetime = Field(..., example="2024-08-01T18:00:00Z")
    location: str = Field(..., example="Conference Room")
    created_by: str = Field(..., example="alice@example.com")
    invitees: List[str] = Field(default_factory=list)


class CalendarEvent(BaseModel):
    id: int
    title: str
    date: datetime
    status: Optional[RSVPStatus] = None


class Notification(BaseModel):
    id: int
    user_email: str
    message: str
    type: NotificationType
    read: bool = False
    timestamp: datetime


class RSVPResponse(BaseModel):
    invitation_id: int
    status: RSVPStatus


# --------- In-Memory Storage (For Demo) ---------


events_db: List[Event] = []
invitations_db: List[Invitation] = []
notifications_db: List[Notification] = []
id_counter = {"event": 1, "invitation": 1, "notification": 1}


@app.get("/")
def health_check():
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.post("/events/", response_model=Event, status_code=201)
def create_event(request: EventCreateRequest):
    """Create a new event, generate invitations, and notifications for invitees."""
    event_id = id_counter["event"]
    event = Event(
        id=event_id,
        title=request.title,
        description=request.description,
        date=request.date,
        location=request.location,
        created_by=request.created_by,
        invitees=request.invitees,
    )
    events_db.append(event)

    # Create invitations for invitees and notify them
    for email in request.invitees:
        inv_id = id_counter["invitation"]
        invitation = Invitation(
            id=inv_id,
            event_id=event_id,
            invitee_email=email,
            status=RSVPStatus.pending,
        )
        invitations_db.append(invitation)
        id_counter["invitation"] += 1

        # Send notification
        notif_id = id_counter["notification"]
        notif = Notification(
            id=notif_id,
            user_email=email,
            message=(
                f"You are invited to '{event.title}' "
                f"on {event.date.strftime('%Y-%m-%d %H:%M')}."
            ),
            type=NotificationType.reminder,
            timestamp=datetime.utcnow(),
            read=False,
        )
        notifications_db.append(notif)
        id_counter["notification"] += 1

    id_counter["event"] += 1
    return event


# PUBLIC_INTERFACE
@app.get("/events/", response_model=List[Event])
def list_events():
    """List all events (for demonstration purposes, no authentication)."""
    return events_db


# PUBLIC_INTERFACE
@app.get("/events/{event_id}", response_model=Event)
def get_event(event_id: int):
    """Get single event details."""
    for event in events_db:
        if event.id == event_id:
            return event
    raise HTTPException(status_code=404, detail="Event not found")


# PUBLIC_INTERFACE
@app.get("/events/{event_id}/invitations", response_model=List[Invitation])
def get_event_invitations(event_id: int):
    """Get all invitations for a specific event."""
    return [i for i in invitations_db if i.event_id == event_id]


# PUBLIC_INTERFACE
@app.post("/invitations/{invitation_id}/rsvp", response_model=Invitation)
def rsvp_invitation(invitation_id: int, status: RSVPStatus):
    """RSVP to an invitation and send notifications to event organizer."""
    invitation = next((i for i in invitations_db if i.id == invitation_id), None)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invitation.status = status

    # Find related event
    event = next((e for e in events_db if e.id == invitation.event_id), None)
    if event:
        # Notify event organizer
        notif_id = id_counter["notification"]
        notif = Notification(
            id=notif_id,
            user_email=event.created_by,
            message=(
                f"{invitation.invitee_email} has "
                f"{status.value} your invitation for '{event.title}'."
            ),
            type=NotificationType.update,
            timestamp=datetime.utcnow(),
            read=False,
        )
        notifications_db.append(notif)
        id_counter["notification"] += 1

    return invitation


# PUBLIC_INTERFACE
@app.get("/calendar/{user_email}", response_model=List[CalendarEvent])
def get_calendar_events(user_email: str):
    """Get a user's upcoming and past events for calendar view (accepted/invited)."""
    user_events = []
    for invitation in invitations_db:
        if (
            invitation.invitee_email == user_email
            and invitation.status in [RSVPStatus.accepted, RSVPStatus.pending]
        ):
            event = next(
                (e for e in events_db if e.id == invitation.event_id),
                None
            )
            if event:
                user_events.append(
                    CalendarEvent(
                        id=event.id,
                        title=event.title,
                        date=event.date,
                        status=invitation.status,
                    )
                )
    # Add events created by user as well
    for event in events_db:
        if event.created_by == user_email:
            user_events.append(
                CalendarEvent(
                    id=event.id,
                    title=event.title,
                    date=event.date,
                    status=None,
                )
            )
    return sorted(user_events, key=lambda x: x.date)


# PUBLIC_INTERFACE
@app.get("/notifications/{user_email}", response_model=List[Notification])
def get_notifications(user_email: str, unread_only: bool = False):
    """Return all notifications for a user."""
    notes = [n for n in notifications_db if n.user_email == user_email]
    if unread_only:
        notes = [n for n in notes if not n.read]
    return sorted(notes, key=lambda n: n.timestamp, reverse=True)


# PUBLIC_INTERFACE
@app.post("/notifications/{notification_id}/read", response_model=Notification)
def mark_notification_as_read(notification_id: int):
    """Mark notification as read."""
    notification = next(
        (n for n in notifications_db if n.id == notification_id),
        None
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = True
    return notification


# PUBLIC_INTERFACE
@app.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int):
    """Delete an event and its invitations/notifications."""
    event = next((e for e in events_db if e.id == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    events_db.remove(event)
    # Remove invitations and notifications
    global invitations_db
    global notifications_db
    invitations_db = [i for i in invitations_db if i.event_id != event_id]
    notifications_db = [
        n for n in notifications_db
        if not (
            n.type in [NotificationType.reminder, NotificationType.update]
            and ((
                "You are invited" in n.message
                and f"'{event.title}'" in n.message
            ) or (
                "your invitation for" in n.message
                and f"'{event.title}'" in n.message
            ))
        )
    ]
    return

