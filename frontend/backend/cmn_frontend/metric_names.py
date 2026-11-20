"""Plain-language names of the thesis metrics, for clinicians (v3).

The thesis app's own labels are technical ("Crisis-line domain hits", "Hourly CV", "Down/Up byte
ratio"), and its codes ("C9_F1_CrisisLineHits") mean nothing to a clinician. Every place the portal
names a metric (configuration, flags, charts, the assistant's context) uses these names instead. A
metric without an entry gets a readable name built from its code, never the code itself.
"""

from __future__ import annotations

import re

PLAIN: dict[str, str] = {
    # C1 depressed mood (shared "F" metrics)
    "F1_DistinctSocial": "Different social and messaging services",
    "F2_MeanSocialDurSec": "Average time per social-media session",
    "F3_LongStreams": "Long streaming sessions (2 h or more)",
    "F4_DownUpRatio": "Received compared with sent (watching vs. writing)",
    "F5_RevisitRatio": "Share of sites opened again the same day",
    "F6_Fano": "How bursty the use is (short repeated bursts)",
    "F7_HourlyCV": "How uneven the use is across the hours of the day",
    "F8_NightDayRatioPkts": "Share of the day's use falling at night",
    "IS": "Same rhythm from day to day",
    "IV": "Switching between use and pauses within a day",
    "ND_Ratio": "Night use compared with day use",
    "LateNightShare": "Share of use late at night",
    "ActiveNightMinutes": "Minutes in use at night (00–05)",
    "LongestInactivityHours": "Longest stretch without use (h)",
    # C2 loss of interest
    "C2_F1_UniqueSLD": "Different websites and services",
    "C2_F2_MedianReplyLatencySec": "Time until replying in chats",
    "C2_F3_ChatSessionCount": "Chat sessions",
    "C2_F4_MeanUpstreamRateBps": "Amount sent in chats (messages, voice, photos)",
    "C2_F5_PassiveActiveByteRatio": "Watching compared with writing or posting",
    "C2_F6_ProductivityHits": "Use of work and study tools",
    "C2_F7_SocialOutgoingShareUp": "Share of social-media use spent posting",
    # C3 appetite
    "C3_F1_FoodDeliveryHits": "Food-delivery services used",
    "C3_F2_LateNightDeliveryRatio": "Share of food orders late at night (22–06)",
    "C3_F3_MeanInterOrderDays": "Time between food orders",
    "C3_F4_DietSiteVisits": "Diet and nutrition sites",
    "C3_F5_TrackerBurstCount": "Calorie-tracker use",
    "C3_F6_SmartScaleUploads": "Smart-scale weigh-ins",
    "C3_F7_WeighInTimeVarMin": "Variation in weigh-in time (min)",
    # C4 sleep
    "C4_F1_OnsetDelayFrom2200Min": "Devices went quiet after 22:00 (min later)",
    "C4_F2_WakeAfter0400Min": "First use after 04:00 (min later)",
    "C4_F3_OnsetVar14dMin": "Variation in when devices go quiet (14 days, min)",
    "C4_F4_SleepDurationZAbs30d": "Quiet window at night unlike the last 30 days",
    "C4_F5_NocturnalMicroSessionCount0106": "Short checks at night (01–06)",
    "C4_F6_MeanInterAwakGapMin0106": "Time between night-time checks (01–06, min)",
    "C4_F7_DaytimeIdleRatio0818": "Share of the day without use (08–18)",
    "C4_F8_NightDayTrafficRatioBytes": "Share of the day's data used at night",
    # C5 restlessness
    "C5_F1_DhcpPerHour": "Devices reconnecting to the Wi-Fi per hour",
    "C5_F2_WifiDwellMin": "Time between Wi-Fi reconnections (min)",
    "C5_F3_MedianIKS": "Typing pauses in chats (s)",
    "C5_F4_IKSStd": "Variation in typing speed (s)",
    "C5_F5_Sub30sSessions": "Very short sessions (under 30 s)",
    "C5_F6_SessionFano": "How irregular session lengths are",
    # C6 energy
    "C6_F1_LongestMiddayIdleMin": "Longest afternoon stretch without use (12–18, min)",
    "C6_F2_DayActiveSessionCount": "Sessions during the day (09–18)",
    "C6_F3_DayIdleRatio_09_18": "Share of the day without use (09–18)",
    "C6_F4_UpstreamBpsPerActiveHour": "Amount sent per hour of use",
    "C6_F5_PostChatCount": "Messages and posts sent",
    "C6_F6_MedianInterReqSec": "Pauses between actions (s)",
    "C6_F7_InterReqFano": "How irregular the pauses between actions are",
    "C6_F8_FirstActivityMin": "First use of the day (after 04:00)",
    "C6_F9_ActivationDelayVsBase28d": "First use later than in the last 4 weeks (min)",
    # C7 worthlessness / guilt
    "C7_F1_MentalHealthSiteVisitsDay": "Mental-health information sites",
    "C7_F2_NegativeSelfSearchRatio": "Searches with negative self-talk",
    "C7_F3_SelfAssessmentDwellSec": "Time on self-tests (s)",
    "C7_F4_HelpTherapyLookupHits": "Help-line and therapy look-ups",
    "C7_F5_AccountDeleteUnsubCount": "Accounts deleted or unsubscribed",
    "C7_F6_SettingsPrivacyDwellSec": "Time on settings and privacy pages (s)",
    "C7_F7_SocialOutgoingShareUp": "Share of social-media use spent posting",
    "C7_F8_CloudUploadBytesToday": "Uploads to cloud storage, more than usual (MB)",
    # C8 concentration
    "C8_F1_MedianPageDwellSec": "Time spent per page (s)",
    "C8_F2_DNSBurstRatePerHour": "Many sites opened in quick succession",
    "C8_F3_NotificationMicroSessionsCount": "Short checks after notifications",
    "C8_F4_RepeatedQueryRatio60m": "Same sites opened again and again",
    "C8_F5_QueryReformulationMax": "Searches rephrased again and again",
    "C8_F6_BackNavShare": "Going back to the previous page",
    "C8_F7_SERPTimeToFirstClickSec": "Time to choose a search result (s)",
    "C8_F8_MedianIKSsec": "Typing pauses (s)",
    # C9 suicidality (counts of sites by hostname, never content)
    "C9_F1_CrisisLineHits": "Crisis-line sites",
    "C9_F2_SuicideMethodQueryRatio": "Searches about suicide methods",
    "C9_F3_TherapyBookingVisits": "Therapy-booking sites",
    "C9_F4_SelfHarmForumVisits": "Self-harm forums",
    "C9_F5_SelfHarmForumUpBytes": "Posts to self-harm forums (MB sent)",
    "C9_F6_SelfHarmForumMeanSessLenSec": "Time per visit to self-harm forums (min)",
    "C9_F7_WillInsuranceDownloads": "Will or insurance documents downloaded",
    "C9_F8_CloudBackupUpBytesToday": "Cloud backup, more than usual (MB)",
    "C9_F9_AccountDeletionRequestsCount": "Accounts deleted",
    "C9_F10_NightSuicideQueryBursts": "Night-time searches about suicide",
    "C9_F11_NightNegativeSearchRatio": "Night-time searches with negative content",
}

# Sites whose daily number is a packet count in the thesis code; the portal shows visits instead.
SITE_GROUP_OF: dict[str, str] = {
    "C9_F1_CrisisLineHits": "crisis",
    "C9_F3_TherapyBookingVisits": "therapy",
    "C7_F1_MentalHealthSiteVisitsDay": "mental_health",
    "C7_F4_HelpTherapyLookupHits": "therapy",
}


def readable(code: str) -> str:
    """A readable name from a code without an entry: "C4_F9_SomeNewMetricMin" -> "Some new metric (min)"."""
    core = re.sub(r"^(C\d_)?F\d+_", "", code)
    unit = ""
    m = re.search(r"(Sec|Min|Bps|Bytes|Hours)$", core)
    if m:
        unit = {"Sec": " (s)", "Min": " (min)", "Bps": "", "Bytes": "", "Hours": " (h)"}[m.group(1)]
        core = core[: m.start()]
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|_", " ", core).strip().lower()
    return (words[:1].upper() + words[1:] + unit) if words else code


def plain(code: str) -> str:
    return PLAIN.get(code) or readable(code)


def plain_labels(codes) -> dict[str, str]:
    return {c: plain(c) for c in codes}
