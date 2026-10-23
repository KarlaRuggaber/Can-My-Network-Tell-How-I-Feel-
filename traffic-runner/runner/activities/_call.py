"""Shared engine of video_call and voice_call (catalog §2): a WebRTC call against the
counterpart on the peer VM (peer-vm/), which is outside the home network, so the media
flows through the gateway in both directions.

The runner asks the peer to join a room derived from the run (profile/seed/block_id and the
secret token), joins the same room with a fake camera/microphone, and stays until the
block ends. A call that drops for three checks in a row fails the run (watch_media).

--mic-share p (profile option mic_share, e.g. 0.1 for social anxiety): the microphone is on
only about p of the time. The call starts muted; the runner unmutes for "speaking" turns of
3-15 s, separated by muted pauses drawn from an exponential distribution whose mean makes
the long-run share p (p = 0.1: ~81 s). The whole schedule is drawn from the seed before the
call. The camera is not affected.
"""

from .. import peer as peer_client

MIC_TALK = (3.0, 15.0)


def mic_schedule(rng, duration, share):
    """[(muted_seconds, talking_seconds), ...] covering `duration`; [] = mic always on."""
    if share >= 1.0:
        return []
    mean_talk = sum(MIC_TALK) / 2
    mean_muted = mean_talk * (1.0 - share) / share
    schedule, t = [], 0.0
    while t < duration:
        muted, talk = rng.expovariate(1.0 / mean_muted), rng.uniform(*MIC_TALK)
        schedule.append((muted, talk))
        t += muted + talk
    return schedule


def run_call(ctx, rng, duration, video):
    schedule = mic_schedule(rng, duration, ctx.overrides.get("mic_share", 1.0))  # before any network
    peer = peer_client.from_env()  # not_implemented if the VM is not configured
    room = peer.room_for(ctx.run_key)
    peer.request_join(room, duration, video)
    ctx.join_call(peer.call_url(room, video, "runner", audio_muted=bool(schedule)))
    for muted, talk in schedule:
        ctx.watch_media(15.0, max_seconds=muted)
        if ctx.remaining() <= 0:
            break
        ctx.set_mic(True)
        ctx.watch_media(15.0, max_seconds=talk)
        if ctx.remaining() <= 0:
            break
        ctx.set_mic(False)
    ctx.watch_media(15.0)
    return ctx.visited
