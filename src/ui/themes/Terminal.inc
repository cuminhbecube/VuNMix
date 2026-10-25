namespace terminal {
using namespace v;
constexpr uint32_t BG=0x020805,GREEN=0x8AFFAC,SOFT=0x79B58B,DIM=0x365F43,TRACK=0x173522,FOCUS=0x0C2415;
void txt(lv_obj_t* s,int x,int y,int w,const char* value,const lv_font_t* f=mono,uint32_t ink=GREEN,lv_text_align_t align=LV_TEXT_ALIGN_LEFT){text(s,x,y,w,value,f,ink,align);}
void rule(lv_obj_t* s,int y,uint32_t color=DIM){box(s,8,y,304,1,color);}
void meter(lv_obj_t* s,int x,int y,int w,int h,int val,int count=19,uint32_t ink=GREEN){
    int on=(clamp(val)*count+50)/100;for(int i=0;i<count;i++){int a=x+w*i/count,b=x+w*(i+1)/count;box(s,a,y,b-a-2,h,i<on?ink:TRACK);}}
void header(lv_obj_t* s,const char* title,bool online=true){reset(s,BG);logo(s,8,6);txt(s,36,8,200,title);
    txt(s,248,8,64,online?"LINK":"OFF",mono,online?GREEN:SOFT,LV_TEXT_ALIGN_RIGHT);rule(s,32,GREEN);
    if(m.page!=Page::Offline){const char* modes[]={"OUT","IN","APP","MIX","PC"};int xs[]={8,72,120,184,248};
        for(int i=0;i<5;i++){txt(s,xs[i],40,48,modes[i],mono,i==m.mode-1?GREEN:SOFT);
            if(i==m.mode-1)box(s,xs[i],59,i==1||i==4?32:48,2,GREEN);}rule(s,63);}}
void audio(lv_obj_t* s){bool muted=m.current.muted;header(s,modeName(),m.pcConnected);
    txt(s,8,74,48,"SRC",mono,SOFT);txt(s,72,74,240,name(m.current),vn14);txt(s,8,98,304,currentRole(),f12,SOFT);
    txt(s,8,124,48,"VOL");box(s,72,116,80,32,muted?SOFT:GREEN);txt(s,72,124,80,volume(m.current,true),mono,BG,LV_TEXT_ALIGN_CENTER);
    txt(s,184,124,128,muted?"MUTED":"MUTE 0",mono,muted?GREEN:SOFT,LV_TEXT_ALIGN_RIGHT);meter(s,8,156,304,12,m.current.volume,19,muted?SOFT:GREEN);
    if(m.mode==3){txt(s,8,185,304,mediaStatus(),f12,SOFT);txt(s,8,209,304,mediaTitle(),vn14);}
    else{txt(s,8,184,48,"SIG",mono,SOFT);txt(s,72,184,64,fmt("%u%%",m.meterCurrent));meter(s,144,187,168,9,m.meterCurrent,16);
        rule(s,214);txt(s,8,222,304,muted?"Stored volume retained while muted":"Volume and signal are independent",f12,SOFT);}}
void select(lv_obj_t* s){header(s,m.mode==4?(m.selectChannel=='B'?"SELECT B":"SELECT A"):m.mode==3?"BROWSE APP":m.mode==2?"BROWSE IN":"BROWSE OUT",m.pcConnected);
    txt(s,8,73,176,"SESSION",mono,SOFT);txt(s,216,73,48,"VOL",mono,SOFT);txt(s,280,73,32,"D",mono,SOFT,LV_TEXT_ALIGN_RIGHT);
    for(int i=0;i<3;i++){const auto& a=slot(i);int y=100+i*34;if(i==1){box(s,8,y-4,304,28,FOCUS);box(s,8,y-4,2,28,GREEN);txt(s,12,y,16,">");}
        txt(s,36,y+1,172,name(a),vn14,i==1?GREEN:SOFT);txt(s,216,y,64,volume(a,true),mono,i==1?GREEN:SOFT);
        if(a.isDefault)txt(s,280,y,32,"*",mono,GREEN,LV_TEXT_ALIGN_RIGHT);rule(s,y+27);}
    txt(s,8,206,304,"* WINDOWS DEFAULT / > FOCUSED",f12,SOFT);txt(s,8,224,304,"Previous / selected / next",f12,GREEN);}
void game(lv_obj_t* s){header(s,"GAME MIX",m.pcConnected);txt(s,8,77,48,"A >");txt(s,72,77,240,name(m.alternate),vn14);
    meter(s,8,108,232,12,m.alternate.volume,15);txt(s,248,105,64,volume(m.alternate,true));
    txt(s,8,132,304,m.alternate.muted?"CHANNEL A / MUTED / ADJUSTING":"CHANNEL A / ADJUSTING",f12,SOFT);rule(s,153);
    txt(s,8,166,48,"B",mono,SOFT);txt(s,72,166,240,name(m.current),vn14,SOFT);meter(s,8,197,232,12,m.current.volume,15,SOFT);
    txt(s,248,194,64,volume(m.current,true),mono,SOFT);txt(s,8,221,304,m.current.muted?"CHANNEL B / MUTED":"CHANNEL B / READY",f12,SOFT);}
void health(lv_obj_t* s){header(s,"PC STATUS",m.pcConnected);const char* labels[]={"CPU","GPU","RAM"};unsigned vals[]={m.cpu,m.gpu,m.ram};
    for(int i=0;i<3;i++){int y=78+i*34;txt(s,8,y,48,labels[i],mono,SOFT);txt(s,80,y,64,stats(vals[i]));
        if(i<2){meter(s,152,y+4,72,8,m.statsValid?vals[i]:0,6);txt(s,248,y,64,temp(i?m.gpuTemp:m.cpuTemp),f12,SOFT,LV_TEXT_ALIGN_RIGHT);}
        else txt(s,152,y+2,160,ramInfo(),f14,SOFT,LV_TEXT_ALIGN_RIGHT);rule(s,y+27);}
    txt(s,8,188,48,"NET",mono,SOFT);txt(s,72,191,240,netBoth(),f12,GREEN);rule(s,213,GREEN);txt(s,8,223,304,debugInfo(),f12,SOFT);}
void offline(lv_obj_t* s){header(s,"VUNMIX",false);txt(s,8,59,304,"PC LINK OFFLINE");rule(s,89);
    txt(s,8,111,304,"WAITING FOR PC");txt(s,8,147,304,"Open VuNMix on your computer",vn14,SOFT);
    box(s,8,185,10,16,GREEN);txt(s,32,186,280,"Desktop connection required",f12,SOFT);rule(s,219,GREEN);}
void draw(lv_obj_t* s){switch(m.page){case Page::Audio:audio(s);break;case Page::Select:select(s);break;
    case Page::Game:game(s);break;case Page::Health:health(s);break;case Page::Offline:offline(s);break;}}
}
