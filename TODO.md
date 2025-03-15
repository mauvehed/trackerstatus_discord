# TrackerStatus Discord Bot TODO

## High Priority
1. Fix Tracker Command Issues
   - [ ] Debug and fix `trackerlatency` command failures
   - [ ] Debug and fix `trackeruptime` command failures
   - [ ] Debug and fix `trackerrecord` command failures
   - [ ] Investigate if fixes are needed in upstream `trackerstatus` library
   - [ ] Add better error handling and user feedback for failed commands

2. Improve Status Change Messages
   - [ ] Update status change notifications to include detailed service information
   - [ ] Show count of services up/down in status messages
   - [ ] Include specific service state changes in notifications
   - [ ] Add timestamp of last successful check for each service

## Feature Enhancements
3. Additional API Integration
   - [ ] Review available top-level API endpoints not currently utilized
   - [ ] Consider adding commands for:
     - [ ] Historical status information
     - [ ] Service-specific statistics
     - [ ] Aggregate status information
   - [ ] Evaluate which additional data would be most useful to users

4. Configurable Status Notifications
   - [ ] Add guild-level configuration for notification preferences
   - [ ] Allow per-tracker notification settings
   - [ ] Support configuration options:
     - [ ] Toggle notifications for Online/Offline transitions
     - [ ] Toggle notifications for Unstable state
     - [ ] Custom notification thresholds
   - [ ] Add command to manage notification settings
   - [ ] Persist notification preferences in config file

5. Dynamic Status Display
   - [ ] Implement persistent status embed
   - [ ] Add auto-updating functionality for embed
   - [ ] Include:
     - [ ] Overall tracker status
     - [ ] Individual service statuses
     - [ ] Last update timestamp
     - [ ] Uptime statistics
   - [ ] Add command to create/manage status embed
   - [ ] Handle embed persistence across bot restarts

## Future Considerations
- Consider adding alert throttling for frequent status changes
- Add support for custom notification messages
- Implement status history visualization
- Add support for webhook notifications as an alternative to channel messages
- Consider adding role mentions for specific status changes

## Notes
- Some features may require updates to the `trackerstatus` library
- Need to maintain backwards compatibility with existing configurations
- Consider performance implications of new features
- Document all new features and configuration options in README 