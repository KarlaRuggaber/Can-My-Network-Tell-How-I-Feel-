"""Shared engine of video_call and voice_call (catalog §2): a WebRTC call against the
counterpart on the peer VM (peer-vm/), which is outside the home network, so the media
flows through the gateway in both directions.

The runner asks the peer to join a room derived from the run (profile/seed/block_id and the
secret token), joins the same room with a fake camera/microphone, and stays until the
block ends. A call that drops for three checks in a row fails the run (watch_media).
"""

from .. import peer as peer_client


def run_call(ctx, duration, video):
    peer = peer_client.from_env()  # not_implemented if the VM is not configured
    room = peer.room_for(ctx.run_key)
    peer.request_join(room, duration, video)
    ctx.join_call(peer.call_url(room, video, "runner"))
    ctx.watch_media(check_every=15.0)
    return ctx.visited
