
I currently have some supplemental processes that are governed through agent guidelines, templated responses, skills and hooks in vuoro substrate, e.g. /projects/dev/agentops, and in appservice, e.g. /projects/dev/appservice/docs/training/health-checks

These capture following categories of issues from my perspective:
- knowledge gathering of routine operations, formalized shape of actions for later agent re-use
-- e.g. rediscover a remediating action from cluster health checks
- gathering process success and work criteria, cost indicators, rework indicators, failure notes
-- inform e.g. on workflow change success or failure, indicate needs for improvements in processes themselves
- governance notes, e.g. this session worked on this topic and reached this state, populated these events and backlog entry claims
-- largely later reference for working sessions, potential reference for cross-work summarization and analysis
- handover session notes, summary notes, cross-agent session notes
-- common task to e.g. at end of the day require passing workflow to background processes / daemons for completion, summarize session for re-pickup next day, take a longer break
-- same class of work is avoiding context rot by requiring frequent session summary in interactive mode, run /clear, and copy the previous summary to the next session
--- this is operationally the most common pass-over case that is gathered from interactive sessions for follow-on work

Additional problem is that -resume needs a session ID or crawling through a list of sessions to determine last session to copy from, and more importantly *sessions are context and repository specific*. A session finished on workstation in sprintctl repo pwd can't be directly seen from agentops in workstation, and even less on devbox.

Kctl, auditctl, actionq, sprintctl partly respond to these same issues by capturing and reading session shaped metadata, but the core shape of the problem is slightly differently shaped than their reader implementations. At the core of the issue would be to capture a configured set of session work, metadata, and outcome notes as stable trace entries, allow for session visibility cross system and cross repository (at least in project context), and later allow for stable projections for e.g. knowledge capture, audit capture, commit and PR metadata, cost analytics, process analysis, etc.

Primary focus though is on the operational aspects and needs.