"""Reusable, accessible story cards. No sequences, camera motion, or flashing."""
import textwrap
from ursina import Entity, Text, camera, color
from game.ui.main_menu import TEXT_COLOR, ACCENT_COLOR


class StoryScreen(Entity):
    card_seconds = 7

    def __init__(self):
        super().__init__(parent=camera.ui, enabled=False, ignore_paused=True, z=-.6)
        self.background = Entity(parent=self, model='quad', color=color.black, z=.1)
        self.content = Entity(parent=self)
        self.title_text = Text(parent=self.content, origin=(-.5,.5), x=-.52, y=.28, color=TEXT_COLOR)
        self.title_text.base_font = 1.3
        self.body = Text(parent=self.content, origin=(-.5,.5), x=-.52, y=.12, color=TEXT_COLOR)
        self.footer = Text(parent=self.content, origin=(-.5,.5), x=-.52, y=-.31, color=ACCENT_COLOR)
        self.text_scale = 1
        self.cards = []
        self.elapsed = 0
        self.kind = None

    @property
    def duration(self):
        return len(self.cards)*self.card_seconds

    def begin(self, kind, cards):
        self.kind, self.cards, self.elapsed = kind, cards, 0
        self._shown_card = None
        self.refresh()

    def advance(self, dt):
        self.elapsed = min(self.duration, self.elapsed+max(0,dt))
        self.refresh()
        return self.elapsed >= self.duration-1e-8

    def refresh(self):
        if not self.cards:
            return
        index = min(len(self.cards)-1, int(self.elapsed/self.card_seconds))
        signature = (index,self.text_scale,self.kind)
        if signature == getattr(self,'_shown_card',None):
            return
        self._shown_card = signature
        card = self.cards[index]
        self.title_text.text = textwrap.fill(card['title'], width=int(34/self.text_scale))
        self.body.text = textwrap.fill(card['text'], width=int(56/self.text_scale))
        self.footer.text = f'{index+1}/{len(self.cards)}   Enter / Escape: skip'
        if self.kind == 'intro' and index == len(self.cards)-1:
            self.background.color = color.rgba32(0,0,0,145)
        else:
            self.background.color = color.black

    def resize(self, aspect):
        self.background.scale = (aspect,1)
        self.content.scale = min(1,(aspect-.08)/1.15)
        self.title_text.scale = 1.3*self.text_scale
        self.body.scale = .95*self.text_scale
        self.footer.scale = .75*self.text_scale
        self._shown_card = None
        self.refresh()

    def handle(self, key):
        pass  # GameManager owns skip and restores control atomically.
