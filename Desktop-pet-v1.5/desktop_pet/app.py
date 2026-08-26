from __future__ import annotations

import math, random, time, tkinter as tk
from collections import deque
from enum import Enum
from .config import load_config, save_config
from .sprites import SpritePlayer
from .windows import (ActivityPoller, area_at, clamp_to_area, cursor_position,
                      external_edges, monitor_work_areas, nearest_area,
                      set_window_position)


class Mode(str, Enum):
    NORMAL = "NORMAL"
    HIDE_AND_SEEK = "HIDE_AND_SEEK"
    DO_NOT_DISTURB = "DO_NOT_DISTURB"


class Behavior(str, Enum):
    IDLE="IDLE"; WALK="WALK"; TYPING="TYPING"; MOUSE="MOUSE"; CLICK="CLICK"
    SLEEP="SLEEP"; WAKE="WAKE"; EXPRESSION="EXPRESSION"; DRAG="DRAG"
    HIDING="HIDING"; REVEAL="REVEAL"


class DesktopPetApp:
    SIZE=180; TRANSPARENT="#ff00ff"; HIDE_SECONDS=30; HIDE_VISIBLE=42

    def __init__(self):
        self.root=tk.Tk(); self.root.title("双屏桌宠 v1.5"); self.root.overrideredirect(True)
        self.root.attributes("-topmost",True); self.root.attributes("-transparentcolor",self.TRANSPARENT)
        self.root.configure(bg=self.TRANSPARENT); self.root.geometry(f"{self.SIZE}x{self.SIZE}+0+0")
        self.canvas=tk.Canvas(self.root,width=self.SIZE,height=self.SIZE,bg=self.TRANSPARENT,highlightthickness=0)
        self.canvas.pack(); self.config=load_config(); self.sprites=SpritePlayer(self.root)
        self.activity=ActivityPoller(); self.areas=monitor_work_areas()
        self.mode=Mode.DO_NOT_DISTURB if self.config["do_not_disturb"] else Mode.NORMAL
        self.behavior=Behavior.IDLE; self.behavior_since=time.monotonic(); self.facing="right"; self.frame=0
        self.last_key=0.; self.last_mouse=0.; self.key_times=deque(maxlen=30)
        self.target=None; self.drag_offset=None; self.drag_previous_x=None
        self.animation_override="loaf" if self.mode==Mode.DO_NOT_DISTURB else None
        self.expression_until=0.; self.pending_expression=None; self.hide_timeout_id=None
        self.hide_area=None; self.pre_hide_position=None; self.bubble=None; self.bubble_timeout_id=None
        self.root.bind("<ButtonPress-1>",self._left_press); self.root.bind("<B1-Motion>",self._drag_move)
        self.root.bind("<ButtonRelease-1>",self._drag_end); self.root.bind("<Button-3>",self._show_menu)
        self._build_menu(); self.root.after(120,self._initial_position); self.root.after(33,self._tick)
        self.root.after(3000,self._decide)

    def run(self): self.root.mainloop()

    def _build_menu(self):
        self.menu=tk.Menu(self.root,tearoff=False,postcommand=self._prepare_menu)
        self.menu.add_command(label="去散步",command=self._choose_walk)
        self.menu.add_command(label="停止当前动作 / 回到待机",command=self._return_to_idle)
        self.menu.add_separator(); self.expressions=tk.Menu(self.menu,tearoff=False)
        for label,anim,duration in (("开心 / 骄傲","proud",2.5),("舔毛","groom",4.),
            ("打哈欠","yawn",3.),("安静趴卧","loaf",4.),("送你礼物","gift",3.),
            ("开心玩耍","play",4.),("伸懒腰","stretch",3.5)):
            self.expressions.add_command(label=label,command=lambda a=anim,d=duration:self._request_expression(a,d))
        self.menu.add_cascade(label="选择表情",menu=self.expressions)
        self.menu.add_command(label="开始躲猫猫",command=self._start_hide)
        self.menu.add_separator(); self.dnd_var=tk.BooleanVar(value=self.mode==Mode.DO_NOT_DISTURB)
        self.menu.add_checkbutton(label="工作免打扰",variable=self.dnd_var,command=self._toggle_dnd)
        self.menu.add_command(label="设置…",command=self._settings_window); self.menu.add_separator()
        self.menu.add_command(label="退出桌宠",command=self.root.destroy)

    def _prepare_menu(self):
        hiding=self.mode==Mode.HIDE_AND_SEEK; dnd=self.mode==Mode.DO_NOT_DISTURB
        self.menu.entryconfigure(0,label="重新选择目的地" if self.behavior==Behavior.WALK else "去散步",
                                 state="disabled" if hiding or dnd else "normal")
        stoppable=not hiding and not dnd and self.behavior not in (Behavior.IDLE,Behavior.DRAG)
        self.menu.entryconfigure(1,state="normal" if stoppable else "disabled")
        self.menu.entryconfigure(3,state="disabled" if hiding else "normal")
        self.menu.entryconfigure(4,label="正在躲猫猫…" if hiding else "开始躲猫猫",
                                 state="disabled" if hiding or dnd else "normal")
        self.dnd_var.set(dnd)

    def _set_behavior(self,b,keep=False):
        if b!=self.behavior: self.behavior=b; self.behavior_since=time.monotonic()
        if b!=Behavior.WALK:self.target=None
        if not keep and b!=Behavior.EXPRESSION:self.animation_override=None

    def _initial_position(self):
        if self.areas:
            a=self.areas[0]
            self._move(a.center_x-self.SIZE//2,a.bottom-self.SIZE)
            if not self.config.get("screen_intro_shown",False):
                self.config["screen_intro_shown"]=True; save_config(self.config)
                self.root.after(350,lambda:self._show_bubble(message=f"已识别 {len(self.areas)} 块屏幕",duration=3000))
    def _position(self): return self.root.winfo_x(),self.root.winfo_y()
    def _move(self,x,y):
        set_window_position(self.root.winfo_id(),int(x),int(y),self.SIZE,self.SIZE)

    def _choose_walk(self):
        if self.mode!=Mode.NORMAL:return
        self.areas=monitor_work_areas() or self.areas; a=random.choice(self.areas)
        x=random.randint(a.left,max(a.left,a.right-self.SIZE)); cx,_=self._position()
        _,cy=self._position(); y=min(max(cy,a.top),a.bottom-self.SIZE)
        self.facing="right" if x>=cx else "left"; self._set_behavior(Behavior.WALK)
        self.target=(x,y)

    def _return_to_idle(self):
        if self.mode!=Mode.NORMAL:return
        self._set_behavior(Behavior.WAKE if self.behavior==Behavior.SLEEP else Behavior.IDLE)

    def _request_expression(self,anim,duration):
        if self.mode==Mode.HIDE_AND_SEEK:return
        if self.behavior==Behavior.SLEEP:
            self.pending_expression=(anim,duration); self._set_behavior(Behavior.WAKE); return
        self._play_expression(anim,duration)
    def _play_expression(self,anim,duration):
        self.animation_override=anim; self.expression_until=time.monotonic()+duration
        self._set_behavior(Behavior.EXPRESSION,keep=True)

    def _toggle_dnd(self):
        enabled=bool(self.dnd_var.get())
        if enabled and self.mode==Mode.HIDE_AND_SEEK:
            self._finish_hide(False,enter_dnd=True); return
        if enabled:
            self.mode=Mode.DO_NOT_DISTURB; self.pending_expression=None; self.animation_override="loaf"
            self._set_behavior(Behavior.IDLE,keep=True)
        else:
            self.mode=Mode.NORMAL; self.animation_override=None; self._set_behavior(Behavior.WAKE)
        self.config["do_not_disturb"]=enabled; save_config(self.config)

    def _start_hide(self):
        if self.mode!=Mode.NORMAL:return
        self.areas=monitor_work_areas() or self.areas
        choices=external_edges(self.areas)
        if not choices:return
        a,edge=random.choice(choices); m=120; v=self.HIDE_VISIBLE
        self.pre_hide_position=self._position()
        facing="right" if edge=="left" else "left" if edge=="right" else self.facing
        bbox=self.sprites.opaque_bbox("crouch",facing) or (37,30,143,180)
        frame_w=next(iter(self.sprites.frames.values())).width() if self.sprites.frames else 105
        frame_h=next(iter(self.sprites.frames.values())).height() if self.sprites.frames else 150
        frame_left=(self.SIZE-frame_w)//2; frame_top=self.SIZE-frame_h
        visible_left=frame_left+bbox[0]; visible_top=frame_top+bbox[1]
        visible_right=frame_left+bbox[2]; visible_bottom=frame_top+bbox[3]
        if edge=="left":
            x=a.left-(visible_right-v); y=random.randint(a.top+m,max(a.top+m,a.bottom-self.SIZE-m)); self.facing="right"
        elif edge=="right":
            x=a.right-(visible_left+v); y=random.randint(a.top+m,max(a.top+m,a.bottom-self.SIZE-m)); self.facing="left"
        else:
            x=random.randint(a.left+m,max(a.left+m,a.right-self.SIZE-m)); y=a.top-(visible_bottom-v)
        self.mode=Mode.HIDE_AND_SEEK; self.hide_area=a; self.animation_override="crouch"
        self._set_behavior(Behavior.HIDING,keep=True); self._move(x,y)
        self.hide_timeout_id=self.root.after(self.HIDE_SECONDS*1000,lambda:self._finish_hide(False))

    def _finish_hide(self,found,enter_dnd=False):
        if self.mode!=Mode.HIDE_AND_SEEK:return
        if self.hide_timeout_id is not None:
            try:self.root.after_cancel(self.hide_timeout_id)
            except tk.TclError:pass
            self.hide_timeout_id=None
        a=self.hide_area or nearest_area(*cursor_position(),self.areas); self.mode=Mode.NORMAL
        self.animation_override="pounce" if found else "yawn"; self._set_behavior(Behavior.REVEAL,keep=True)
        if self.pre_hide_position:
            px,py=self.pre_hide_position
            return_area=area_at(px+self.SIZE//2,py+self.SIZE//2,self.areas) or nearest_area(px,py,self.areas)
            destination=clamp_to_area(px,py,self.SIZE,self.SIZE,return_area)
        else: destination=(a.center_x-self.SIZE//2,a.top+(a.height-self.SIZE)//2)
        self._move(*destination); self.pre_hide_position=None
        msg="找到我啦！🎉" if found else "我在这里呀～"
        self.root.after(100,lambda:self._show_bubble(message=msg))
        self.root.after(900 if enter_dnd else 1800,self._enter_dnd if enter_dnd else self._finish_reveal)
    def _finish_reveal(self):
        if self.behavior==Behavior.REVEAL and self.mode==Mode.NORMAL:self._set_behavior(Behavior.IDLE)
    def _enter_dnd(self):
        self.mode=Mode.DO_NOT_DISTURB; self.dnd_var.set(True); self.config["do_not_disturb"]=True
        save_config(self.config); self.animation_override="loaf"; self._set_behavior(Behavior.IDLE,keep=True)

    def _decide(self):
        now=time.monotonic()
        if self.mode!=Mode.NORMAL or self.behavior in (Behavior.WALK,Behavior.EXPRESSION,Behavior.DRAG,Behavior.REVEAL):pass
        elif now-self.activity.last_activity>120:self._set_behavior(Behavior.SLEEP)
        elif now-self.last_key<1.6:self._set_behavior(Behavior.TYPING)
        elif now-self.last_mouse<1.:self._set_behavior(Behavior.MOUSE)
        elif not self.config["follow_cursor_position"] and random.random()<.48:self._choose_walk()
        else:self._set_behavior(Behavior.IDLE)
        self.root.after(3000,self._decide)

    def _tick(self):
        self.frame+=1; now=time.monotonic(); events=self.activity.poll()
        if self.mode!=Mode.NORMAL or self.behavior in (Behavior.EXPRESSION,Behavior.DRAG,Behavior.REVEAL):events=set()
        if "typing" in events:
            self.last_key=now; self.key_times.append(now)
            self._set_behavior(Behavior.WAKE if self.behavior==Behavior.SLEEP else Behavior.TYPING)
        elif "click" in events and not self._cursor_over_pet():
            self._set_behavior(Behavior.WAKE if self.behavior==Behavior.SLEEP else Behavior.CLICK)
        elif "mouse" in events:
            self.last_mouse=now
            if self.behavior==Behavior.SLEEP:self._set_behavior(Behavior.WAKE)
            elif self.config["follow_cursor_position"] and self.behavior!=Behavior.TYPING:
                self._follow_cursor()
            elif self.behavior not in (Behavior.WALK,Behavior.TYPING):self._set_behavior(Behavior.MOUSE)
        if self.behavior==Behavior.WAKE and now-self.behavior_since>.9:
            if self.pending_expression:
                a,d=self.pending_expression; self.pending_expression=None; self._play_expression(a,d)
            else:self._set_behavior(Behavior.IDLE)
        elif self.behavior==Behavior.EXPRESSION and now>=self.expression_until:
            if self.mode==Mode.DO_NOT_DISTURB:
                self.animation_override="loaf"; self._set_behavior(Behavior.IDLE,keep=True)
            else:self._set_behavior(Behavior.IDLE)
        elif self.behavior in (Behavior.CLICK,Behavior.MOUSE) and now-self.behavior_since>1:self._set_behavior(Behavior.IDLE)
        elif self.behavior==Behavior.TYPING and now-self.last_key>1.8:self._set_behavior(Behavior.IDLE)
        if self.behavior==Behavior.WALK and self.target and self.drag_offset is None:
            x,y=self._position(); tx,ty=self.target; speed=int(self.config["walk_speed"]); dx=tx-x; dy=ty-y
            if abs(dx)>1:self.facing="right" if dx>0 else "left"
            distance=max(1.0,math.hypot(dx,dy)); step=min(speed,distance)
            nx=x+dx/distance*step; ny=y+dy/distance*step
            probe=area_at(int(nx)+self.SIZE//2,int(ny)+self.SIZE//2,self.areas)
            if probe is None:
                current=nearest_area(x+self.SIZE//2,y+self.SIZE//2,self.areas)
                nx,ny=clamp_to_area(nx,ny,self.SIZE,self.SIZE,current)
                self._move(nx,ny); self.facing="left" if self.facing=="right" else "right"
                self._set_behavior(Behavior.IDLE); self.target=None
                self._draw(); self.root.after(33,self._tick); return
            nx,ny=clamp_to_area(nx,ny,self.SIZE,self.SIZE,probe); self._move(nx,ny)
            if distance<=speed:self._move(tx,ty); self._set_behavior(Behavior.IDLE)
        self._draw(); self.root.after(33,self._tick)

    def _animation(self):
        if self.behavior==Behavior.DRAG:return "drag"
        if self.animation_override:return self.animation_override
        if self.behavior==Behavior.WALK:return "walk"
        if self.behavior==Behavior.TYPING:
            return "typingfast" if sum(t>=time.monotonic()-1 for t in self.key_times)>=7 else "typing"
        if self.behavior==Behavior.SLEEP:return "sleep"
        if self.behavior==Behavior.WAKE:return "wakeup"
        if self.behavior==Behavior.CLICK:return "pet"
        if self.behavior==Behavior.MOUSE:return "crouch"
        if self.mode==Mode.DO_NOT_DISTURB:return "loaf"
        return "idle"

    def _draw(self):
        self.canvas.delete("all"); img=self.sprites.frame(self._animation(),time.monotonic()-self.behavior_since,self.facing)
        if img is not None:self.canvas.create_image(self.SIZE//2,self.SIZE,image=img,anchor="s"); return
        b=2*math.sin(self.frame/4) if self.behavior in (Behavior.WALK,Behavior.TYPING) else 0; c=self.canvas
        c.create_oval(59,48+b,82,76+b,fill="#8bd3dd"); c.create_oval(98,48+b,121,76+b,fill="#8bd3dd")
        c.create_oval(52,62+b,128,132+b,fill="#8bd3dd",outline="#29303b",width=3)

    def _cursor_over_pet(self):
        cx,cy=cursor_position(); x,y=self._position(); return x<=cx<x+self.SIZE and y<=cy<y+self.SIZE
    def _follow_cursor(self):
        if self.mode!=Mode.NORMAL:return
        cx,cy=cursor_position(); a=area_at(cx,cy,self.areas) or nearest_area(cx,cy,self.areas)
        tx,ty=clamp_to_area(cx-self.SIZE//2+55,cy-self.SIZE//2+55,self.SIZE,self.SIZE,a)
        x,_=self._position(); self.facing="right" if tx>=x else "left"
        self._set_behavior(Behavior.WALK); self.target=(tx,ty)
    def _left_press(self,e):
        if self.mode==Mode.HIDE_AND_SEEK:self._finish_hide(True); return
        self.drag_offset=(e.x,e.y); self.drag_previous_x=e.x_root; self._set_behavior(Behavior.DRAG)
    def _drag_move(self,e):
        if self.drag_offset:
            if self.drag_previous_x is not None and abs(e.x_root-self.drag_previous_x)>=3:self.facing="right" if e.x_root>self.drag_previous_x else "left"
            self.drag_previous_x=e.x_root
            a=area_at(e.x_root,e.y_root,self.areas) or nearest_area(e.x_root,e.y_root,self.areas)
            x,y=clamp_to_area(e.x_root-self.drag_offset[0],e.y_root-self.drag_offset[1],self.SIZE,self.SIZE,a)
            self._move(x,y)
    def _drag_end(self,e):
        if not self.drag_offset:return
        self.drag_offset=None; self.drag_previous_x=None; x,y=self._position(); a=nearest_area(x+self.SIZE//2,y+self.SIZE//2,self.areas)
        x,y=clamp_to_area(x,y,self.SIZE,self.SIZE,a); self._move(x,y)
        if self.mode==Mode.DO_NOT_DISTURB:self.animation_override="loaf"; self._set_behavior(Behavior.IDLE,keep=True)
        else:self._set_behavior(Behavior.IDLE)
    def _show_menu(self,e):self.menu.tk_popup(e.x_root,e.y_root)
    def _show_bubble(self,message,duration=2200):
        self._hide_bubble(); self.bubble=tk.Toplevel(self.root); self.bubble.overrideredirect(True); self.bubble.attributes("-topmost",True)
        tk.Label(self.bubble,text=message,bg="#20242c",fg="white",padx=12,pady=8).pack()
        self.bubble.update_idletasks(); x,y=self._position(); bw=self.bubble.winfo_reqwidth(); bh=self.bubble.winfo_reqheight()
        bx=x+(self.SIZE-bw)//2; by=y-bh-8
        a=nearest_area(x+self.SIZE//2,y+self.SIZE//2,self.areas)
        bx=min(max(bx,a.left),a.right-bw); by=min(max(by,a.top),a.bottom-bh)
        set_window_position(self.bubble.winfo_id(),bx,by,bw,bh)
        self.bubble_timeout_id=self.root.after(duration,self._hide_bubble)
    def _hide_bubble(self):
        if self.bubble_timeout_id is not None:
            try:self.root.after_cancel(self.bubble_timeout_id)
            except tk.TclError:pass
            self.bubble_timeout_id=None
        if self.bubble:self.bubble.destroy(); self.bubble=None
    def _settings_window(self):
        w=tk.Toplevel(self.root); w.title("桌宠设置"); w.attributes("-topmost",True); body=tk.Frame(w,padx=18,pady=16); body.pack()
        follow=tk.BooleanVar(value=self.config["follow_cursor_position"])
        speed=tk.IntVar(value=self.config["walk_speed"]); dnd=tk.BooleanVar(value=self.mode==Mode.DO_NOT_DISTURB)
        tk.Checkbutton(body,text="位置跟随鼠标移动",variable=follow).grid(row=0,column=0,columnspan=2,sticky="w")
        tk.Label(body,text="移动速度").grid(row=1,column=0); tk.Scale(body,from_=2,to=10,orient="horizontal",variable=speed).grid(row=1,column=1)
        tk.Checkbutton(body,text="启动后保持工作免打扰",variable=dnd).grid(row=2,column=0,columnspan=2,sticky="w")
        def save():
            self.config.update(follow_cursor_position=follow.get(),walk_speed=speed.get()); save_config(self.config); w.destroy()
            if dnd.get()!=(self.mode==Mode.DO_NOT_DISTURB):self.dnd_var.set(dnd.get()); self._toggle_dnd()
        tk.Button(body,text="保存",command=save).grid(row=3,column=0); tk.Button(body,text="取消",command=w.destroy).grid(row=3,column=1)
