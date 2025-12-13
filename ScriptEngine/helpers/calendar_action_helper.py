import datetime
from tzlocal import get_localzone_name
from dateutil import tz as dateutil_tz
from typing import Dict, Tuple, Optional
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.clients.screenplan_api import ScreenPlanAPI, ScreenPlanAPIRequest
from ScriptEngine.common.enums import ScriptExecutionState
from ScriptEngine.common.script_engine_utils import state_eval

script_logger = ScriptLogger()

class CalendarActionHelper:
    def __init__(self) -> None:
        self.api_client = ScreenPlanAPI()

    def _convert_date_to_google_format(self, date_input: Optional[datetime.datetime]) -> Optional[str]:
        """
        Convert datetime object to Google Calendar API format (ISO format string in UTC).
        
        Args:
            date_input: datetime object to convert
            
        Returns:
            ISO format string (YYYY-MM-DDTHH:MM:SS.mmmZ) in UTC with 3-digit milliseconds and Z suffix, or None if input is None/empty
        """
        if not date_input:
            return None
        
        if isinstance(date_input, datetime.datetime):
            # Convert to UTC if timezone-aware, or assume local time if naive
            if date_input.tzinfo is None:
                # Naive datetime - assume it's in local timezone
                local_tz = dateutil_tz.tzlocal()
                date_input = date_input.replace(tzinfo=local_tz)
            
            # Convert to UTC
            utc_dt = date_input.astimezone(dateutil_tz.tzutc())
            
            # Format with 3-digit milliseconds and replace timezone offset with 'Z' for UTC
            # isoformat() will produce something like "2025-12-12T22:30:51.400+00:00"
            # We need to replace "+00:00" with "Z"
            formatted = utc_dt.isoformat(timespec='milliseconds')
            return formatted.replace('+00:00', 'Z')
        else:
            # If it's not a datetime object, log a warning and return None
            script_logger.log(f'Warning: Expected datetime object, got {type(date_input)}')
            return None

    def handle_action(self, action: Dict, state: Dict) -> Tuple[ScriptExecutionState, Dict]:
        """
        Handle calendar action based on calendarActionType.
        
        Args:
            action: Dictionary containing action data with calendarActionType
            state: Current script state dictionary
            
        Returns:
            Tuple of (status, state)
        """
        action_data = action["actionData"]
        calendar_action_type = action_data.get("calendarActionType")
        
        if calendar_action_type == "create":
            return self._handle_create_action(action_data, state)
        elif calendar_action_type == "list":
            return self._handle_list_action(action_data, state)
        else:
            script_logger.log(f'Unknown calendarActionType: {calendar_action_type}')
            script_logger.get_action_log().add_post_file(
                'text',
                'calendarAction-error.txt',
                f'Unknown calendarActionType: {calendar_action_type}'
            )
            return ScriptExecutionState.FAILURE, state

    def _handle_create_action(self, action_data: Dict, state: Dict) -> Tuple[ScriptExecutionState, Dict]:
        """Handle calendar event creation."""
        # Evaluate expressions from state if they contain variables, otherwise use the string directly
        event_start = state_eval(action_data.get("eventStart", ""), {}, state) if action_data.get("eventStart") else ""
        event_end = state_eval(action_data.get("eventEnd", ""), {}, state) if action_data.get("eventEnd") else ""
        event_title = state_eval(action_data.get("eventTitle", ""), {}, state) if action_data.get("eventTitle") else ""
        event_description = state_eval(action_data.get("eventDescription", ""), {}, state) if action_data.get("eventDescription") else ""
        
        # Convert dates to Google Calendar format
        start_date = self._convert_date_to_google_format(event_start)
        end_date = self._convert_date_to_google_format(event_end)
        
        # Build event object for create action
        # Format start and end as GoogleDateObject with dateTime and timeZone
        event = {
            "start": {
                "dateTime": start_date,
                "timeZone": "UTC"
            } if start_date else None,
            "end": {
                "dateTime": end_date,
                "timeZone": "UTC"
            } if end_date else None,
            "description": event_description,
            "summary": event_title,
            "etag": None,  # null for create
            "id": None,  # null for create
            "groupId": None,  # null for create
            "recurrence": None,  # null if none
            "recurringEventId": None  # null for create
        }
        
        # Build payload
        payload = {
            "actionType": "create",
            "events": [event]
        }
        
        pre_log = f'Creating calendar event: {event_title}'
        script_logger.log(pre_log)
        
        request = ScreenPlanAPIRequest(
            request_id=None,
            method='POST',
            request_type='doCalendarAction',
            path='doCalendarAction',
            payload=payload
        )
        
        response = self.api_client.send_request(request)
        
        if response is not None:
            # Store the response (event object) in outputVarName if provided
            output_var_name = action_data.get("outputVarName", "").strip()
            if output_var_name:
                state[output_var_name] = response
            
            script_logger.get_action_log().add_post_file(
                'text',
                'calendarAction-create-log.txt',
                pre_log + '\n' + f'Successfully created calendar event: {event_title}'
            )
            status = ScriptExecutionState.SUCCESS
        else:
            script_logger.get_action_log().add_post_file(
                'text',
                'calendarAction-create-error.txt',
                pre_log + '\n' + f'Failed to create calendar event: {event_title}'
            )
            status = ScriptExecutionState.FAILURE
        
        return status, state

    def _handle_list_action(self, action_data: Dict, state: Dict) -> Tuple[ScriptExecutionState, Dict]:
        """Handle calendar event listing."""
        # Evaluate expressions from state if they contain variables, otherwise use the string directly
        search_list_start = state_eval(action_data.get("searchListStart", ""), {}, state) if action_data.get("searchListStart") else ""
        search_list_end = state_eval(action_data.get("searchListEnd", ""), {}, state) if action_data.get("searchListEnd") else ""
        # Get system timezone (equivalent to Intl.DateTimeFormat().resolvedOptions().timeZone in JS)
        time_zone = get_localzone_name()

        
        # Convert dates to Google Calendar format
        time_min = self._convert_date_to_google_format(search_list_start)
        time_max = self._convert_date_to_google_format(search_list_end)
        
        # Build payload matching the endpoint's expected format
        payload = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": time_zone
        }
        
        pre_log = f'Listing calendar events from {time_min} to {time_max}'
        if time_zone:
            pre_log += f' (timezone: {time_zone})'
        script_logger.log(pre_log)
        
        request = ScreenPlanAPIRequest(
            request_id=None,
            method='POST',
            request_type='getCalendarEvents',
            path='getCalendarEvents',
            payload=payload
        )
        
        response = self.api_client.send_request(request)
        
        if response is not None:
            # Store the response in outputVarName if provided
            # The endpoint returns {singleEvents: [...], recurringEvents: [...]}
            single_events = response.get("singleEvents", [])
            output_var_name = action_data.get("outputVarName", "").strip()
            if output_var_name:
                state[output_var_name] = single_events
            
            script_logger.get_action_log().add_post_file(
                'text',
                'calendarAction-list-log.txt',
                pre_log + '\n' + f'Successfully listed calendar events: {single_events}'
            )
            status = ScriptExecutionState.SUCCESS
        else:
            script_logger.get_action_log().add_post_file(
                'text',
                'calendarAction-list-error.txt',
                pre_log + '\n' + f'Failed to list calendar events'
            )
            status = ScriptExecutionState.FAILURE
        
        return status, state
