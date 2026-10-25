// ORBIT: native circular instrumentation. All values come from the live model.
namespace orbit {
using namespace v;
constexpr uint32_t BG=0x071826,RAIL=0x102637,TRACK=0x1E3C4D,INK=0xEBF8FA,DIM=0x91AFBC,CYAN=0x58D9F3,MINT=0x82E2BC,WARN=0xFFAC9C;
constexpr double PI=3.14159265358979323846;
void ticks(lv_obj_t* s,int cx,int cy,int r,int count) {
    for(int i=0;i<count;i++){double a=2*PI*i/count-PI/2;int len=i%5?3:7;
        line(s,cx+std::lround(std::cos(a)*(r-len)),cy+std::lround(std::sin(a)*(r-len)),
             cx+std::lround(std::cos(a)*r),cy+std::lround(std::sin(a)*r),TRACK);}
}
void heading(lv_obj_t* s,const char* title) {
    reset(s,BG);box(s,282,0,38,240,RAIL);logo(s,291,10);
    const char* labels[]={"OUT","IN","APPS","MIX","INFO"};
    for(int i=0;i<5;i++){int y=49+i*32;if(i==m.mode-1)box(s,282,y-4,3,25,CYAN,1);
        text(s,284,y,36,labels[i],f12,i==m.mode-1?CYAN:DIM,LV_TEXT_ALIGN_CENTER);}
    box(s,288,222,5,5,m.pcConnected?MINT:DIM,3);text(s,297,216,21,"PC",f12,DIM);
    text(s,14,13,254,title,f14,INK);
}
void audio(lv_obj_t* s) {
    heading(s,modeName());ticks(s,100,116,73,30);
    arc(s,35,51,130,m.current.volume,TRACK,m.current.muted?DIM:CYAN,8);
    text(s,49,82,102,volume(m.current),f48,m.current.muted?DIM:INK,LV_TEXT_ALIGN_CENTER);
    text(s,59,137,82,m.current.muted?"% STORED":"% VOLUME",f12,DIM,LV_TEXT_ALIGN_CENTER);
    if(m.mode==3){text(s,183,58,91,m.current.muted?"MUTED":m.mediaValid?(m.mediaPlaying?"PLAYING":"PAUSED"):"NO MEDIA",f12,m.current.muted?WARN:MINT);
        text(s,201,94,48,LV_SYMBOL_AUDIO,f36,MINT,LV_TEXT_ALIGN_CENTER);
        text(s,185,145,85,"GLOBAL",f12,DIM,LV_TEXT_ALIGN_CENTER);
        text(s,14,190,257,name(m.current),vn14,INK);text(s,14,217,257,mediaTitle(),vn14,DIM);
    } else {
        text(s,183,55,92,m.current.muted?"MUTED":m.current.isDefault?"DEFAULT":"DEVICE",f12,m.current.muted?WARN:MINT);
        text(s,186,91,81,"SIGNAL",f12,DIM);text(s,185,114,85,fmt("%u%%",m.meterCurrent),f24,INK);
        for(int i=0;i<10;i++)box(s,187+i*8,152,5,14,i*10<m.meterCurrent?MINT:TRACK,1);
        text(s,14,195,257,name(m.current),vn14,INK);text(s,14,221,257,currentRole(),f12,DIM);
    }
}
void select(lv_obj_t* s) {
    heading(s,selectTitle());line(s,40,76,40,201,TRACK,2);
    for(int i=0;i<3;i++){int y=46+i*62;const auto& a=slot(i);uint32_t ink=i==1?CYAN:a.isDefault?MINT:DIM;
        box(s,13,y,54,54,BG,27);arc(s,14,y+1,52,a.available?a.volume:0,TRACK,ink,3);
        text(s,18,y+12,44,volume(a),f20,INK,LV_TEXT_ALIGN_CENTER);text(s,21,y+34,38,"%",f12,DIM,LV_TEXT_ALIGN_CENTER);
        text(s,80,y+3,194,name(a),vn14,i==1?INK:DIM);text(s,80,y+30,194,role(a,i==1),f12,ink);}
}
void game(lv_obj_t* s) {
    heading(s,"GAME MIXER");
    for(int i=0;i<2;i++){int cx=74+i*132;const auto& a=i?m.current:m.alternate;
        text(s,10+i*132,42,127,name(a),vn14,INK,LV_TEXT_ALIGN_CENTER);ticks(s,cx,127,60,20);
        arc(s,cx-54,73,108,a.available?a.volume:0,TRACK,a.muted?DIM:i?MINT:CYAN,7);
        text(s,cx-46,99,92,volume(a),f36,a.muted?DIM:INK,LV_TEXT_ALIGN_CENTER);
        text(s,cx-45,144,90,a.muted?"MUTED":"%",f12,a.muted?WARN:DIM,LV_TEXT_ALIGN_CENTER);
        text(s,10+i*132,197,128,i?"B / READY":"A / ADJUSTING",f12,i?MINT:CYAN,LV_TEXT_ALIGN_CENTER);}
    text(s,14,222,254,"Double tap: A/B 50%",f12,DIM);
}
void health(lv_obj_t* s) {
    heading(s,"PC HEALTH");const char* names[]={"CPU","GPU","RAM"};unsigned vals[]={m.cpu,m.gpu,m.ram};
    for(int i=0;i<3;i++){int x=8+i*89;text(s,x,41,80,names[i],f14,DIM,LV_TEXT_ALIGN_CENTER);
        arc(s,x,65,80,m.statsValid?vals[i]:0,TRACK,i==1?MINT:CYAN,5);
        text(s,x+6,84,68,stats(vals[i],false),f28,INK,LV_TEXT_ALIGN_CENTER);text(s,x+15,118,50,"%",f12,DIM,LV_TEXT_ALIGN_CENTER);
        text(s,x-2,151,84,i==2?ramInfo():temp(i?m.gpuTemp:m.cpuTemp),f12,DIM,LV_TEXT_ALIGN_CENTER);}
    text(s,14,180,122,"DOWN",f12,DIM);text(s,150,180,122,"UP",f12,DIM);
    text(s,14,199,124,net(false),f16,CYAN);text(s,150,199,124,net(true),f16,MINT);
    text(s,10,224,267,debugInfo(),f12,DIM);
}
void offline(lv_obj_t* s) {
    reset(s,BG);logo(s,14,12);text(s,43,14,130,"VuNMix",f14,INK);
    arc(s,106,51,108,0,TRACK,TRACK,1);arc(s,120,65,80,0,TRACK,TRACK,1);
    text(s,124,83,72,LV_SYMBOL_USB,f36,DIM,LV_TEXT_ALIGN_CENTER);box(s,197,73,8,8,WARN,4);
    text(s,14,175,292,"Waiting for PC",f20,INK,LV_TEXT_ALIGN_CENTER);
    text(s,14,204,292,"Open VuNMix on your computer",f12,DIM,LV_TEXT_ALIGN_CENTER);
    text(s,14,224,292,"PC LINK OFFLINE",f12,WARN,LV_TEXT_ALIGN_CENTER);
}
void draw(lv_obj_t* s) {switch(m.page){case Page::Audio:audio(s);break;case Page::Select:select(s);break;
    case Page::Game:game(s);break;case Page::Health:health(s);break;case Page::Offline:offline(s);break;}}
}
