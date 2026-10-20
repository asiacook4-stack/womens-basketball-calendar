# Women’s NCAA Basketball · 2026–27

**Live subscription:** https://asiacook4-stack.github.io/womens-basketball-calendar/calendar.ics

[Subscription instructions and current status](https://asiacook4-stack.github.io/womens-basketball-calendar/)

This public feed includes every **confirmed matchup** on the official schedules of UConn, South Carolina, UCLA, USC, LSU, Texas, Notre Dame and Duke, including published exhibitions. It adds national spotlight games between a published contender pool: those eight plus Michigan, Maryland, Ohio State, Tennessee, NC State, Louisville, Oklahoma, TCU, Baylor, Iowa State, North Carolina, Ole Miss, Vanderbilt, Iowa and Kentucky. The additional games are sourced from the 22 official team schedules in `sources.json`. This is an editorial national spotlight definition, not a claim to include every televised or ranked game. No ranking is inferred.

Tournament dates without confirmed opponents and intra-squad scrimmages are excluded. Confirmed postseason games will be included when the monitored official schedules publish them. No future bracket opponents are invented.

## Subscribe — Asia and Benjamin each follow these steps

**Mac:** Calendar → File → New Calendar Subscription → paste the HTTPS subscription URL → Subscribe. Choose **iCloud** to make it available on devices using the same Apple Account, and choose **Every hour** in Auto-refresh. Use a different color if desired. Choose America/Los_Angeles in Calendar’s time-zone settings to see Pacific time.

**iPhone/iPad:** Calendar → Calendars → Add Calendar → Add Subscription Calendar → paste the same HTTPS URL → Subscribe. If this path differs on your iOS version, Settings → Apps → Calendar → Calendar Accounts → Add Account → Other → Add Subscribed Calendar is the alternative.

Benjamin subscribes to the same public URL under **his own Apple Account**. No GitHub account or invitation is needed. Do not import a downloaded `.ics` file: importing creates a one-time copy and will not receive updates. If the subscription is already in iCloud, do not add it a second time on the same account.

The feed checks official sources about every six hours. GitHub can delay scheduled jobs. Existing-event changes need two matching observations at least 30 minutes apart, normally the next scheduled run, so a correction may take roughly 6–12 hours plus Apple’s refresh delay. The feed requests a six-hour refresh, but Apple controls actual fetching. Mac offers an Auto-refresh setting and View → Refresh Calendars. iCloud/iPhone delivery is not instant, and the feed cannot force an immediate refresh. Recheck the official event listing close to tipoff.

[Apple subscription help](https://support.apple.com/102301) · [Apple Mac refresh help](https://support.apple.com/guide/calendar/icl1024/mac)

## Times and watching

Timed events include the `America/Los_Angeles` time zone and daylight-saving definitions. Calendar may display them in your current device/calendar time zone. Event notes also show Pacific tipoff explicitly. A game with no published tipoff appears as an all-day **Time TBA** placeholder; midnight is never invented as a tipoff. End times are estimates of 2 hours 15 minutes.

Each event contains the published network, subscription guidance, official source links, and watch URLs when available. An official game deep link is preferred. Otherwise the link is clearly labeled a service/channel page or directory; you may need to find the game. Unknown broadcasts remain TBA. Link checks test HTTPS reachability, **not successful playback or your personal entitlement**. A school-published link that cannot be verified stays labeled unverified in the notes and is not promoted as the main event URL. No streaming credentials are collected or stored.

- **ESPN Unlimited:** ESPN networks, ESPN+, ESPN on ABC, SEC Network+, and ACC Network Extra use your existing ESPN access. [ESPN plan coverage](https://plus.espn.com/)
- **Peacock Premium:** published Peacock games use your existing plan. [Peacock college basketball](https://www.peacocktv.com/sports/college-basketball)
- **B1G+:** separate paid service for its events. Big Ten Network is a different channel. [B1G+ explanation](https://support.bigtenplus.com/hc/en-us/articles/4404943755410-What-is-B1G)
- **FOX/FS1/FS2/BTN:** FOX One or a qualifying TV provider; separate from the two subscriptions above. [FOX coverage](https://www.fox.com/espn)
- **CBS Sports Network:** check a qualifying provider; a Paramount+ subscription alone does not automatically provide this cable channel.
- **UConn+, FloSports, BDG Live, HBO Max/TNT/truTV, MEAC, ION and CW:** follow the published event listing; access varies. No additional subscription has been purchased.

## Update safeguards and maintenance

`update_calendar.py` reads the official schedule pages and the public APIs used by those pages. It does not use ESPN’s unofficial scoreboard as a schedule authority. School-published watch links take priority over directory fallbacks.

- Validates sport/season, dates, complete pagination, and at least 25 season entries for **every** source. A failure blocks the whole publication and leaves the live feed untouched.
- Converts school-local Sidearm times using each school’s time zone; WMT timestamps contain UTC offsets. South Carolina dates/times use the displayed Eastern schedule, not the WordPress sorting timestamp.
- Deduplicates canonical team names and official calendar date, cross-checks tipoff when multiple monitored schools list the same game, and stops if they disagree.
- Uses stable UIDs and sequence numbers; rescheduling retains the UID through official source IDs. South Carolina uses opponent/venue identifiers because its page does not expose a stable numeric event ID.
- Requires two matching observations at least 30 minutes apart before changing an existing game. Mass changes or mass disappearances fail publication for manual review.
- Never deletes a game solely because a source row disappears. Small disappearances retain the last verified event and are counted in status; a published cancellation marks the event cancelled. Postponements are labeled explicitly.
- Retries transient HTTP errors, enforces timeouts, rechecks streaming URLs daily, and validates the generated iCalendar before writing.

The GitHub Actions workflow tests safeguards, fetches updates, commits state and publishes `docs/` to GitHub Pages with HTTPS. It needs no external API keys or paid hosting. See [Actions](https://github.com/asiacook4-stack/womens-basketball-calendar/actions) for failures and `status.json` for last successful publication. GitHub may disable scheduled workflows after prolonged repository inactivity; check Actions if the status becomes stale and re-enable the workflow if necessary. Bot state commits normally keep this repository active, but scheduled execution is not a guaranteed real-time service.

If an athletics site changes its data format, repair its adapter and rerun the tests and workflow. Never publish partial data to clear a failing build. Review pending candidates in `state.json`; do not clear safety gates without comparing official schedules.

## Local validation

Requires Python 3.12: `python -m pip install -r requirements.txt`, `python -m unittest test_calendar -v`, then `python update_calendar.py`.
