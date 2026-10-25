namespace windowsdark {
using namespace v;
constexpr uint32_t BG=0x202020,CHROME=0x1B1B1B,SURFACE=0x2B2B2B,SELECTED=0x30383D,TRACK=0x484848,
    INK=0xF5F5F5,DIM=0xBBBBBB,MUTED=0x919191,CYAN=0x60CDFF,GREEN=0x79D69C,RED=0xFF8B8B;
void shell(lv_obj_t* s,const char* title){reset(s,BG);box(s,0,0,320,28,CHROME);logo(s,8,4);text(s,36,6,224,title,f14,INK);
    box(s,269,12,5,5,m.pcConnected?GREEN:MUTED,3);text(s,280,7,32,m.pcConnected?"USB":"OFF",f12,DIM);
    box(s,0,200,320,40,CHROME);const char* labels[]={"OUT","IN","APPS","MIX","INFO"};
    const char* icons[]={LV_SYMBOL_VOLUME_MAX,LV_SYMBOL_AUDIO,LV_SYMBOL_LIST,LV_SYMBOL_SHUFFLE,LV_SYMBOL_SETTINGS};
    for(int i=0;i<5;i++){bool active=i==m.mode-1;if(active)box(s,i*64+12,200,40,2,CYAN);
        text(s,i*64,207,64,icons[i],f16,active?CYAN:DIM,LV_TEXT_ALIGN_CENTER);text(s,i*64,225,64,labels[i],f12,active?CYAN:DIM,LV_TEXT_ALIGN_CENTER);}}
void audio(lv_obj_t* s){shell(s,modeName());box(s,8,36,304,156,SURFACE,8);text(s,20,47,280,name(m.current),vn14,INK);
    text(s,20,72,280,m.current.isDefault?"Default device":m.mode==3?"Application volume":"Device volume",f12,DIM);
    if(m.current.muted){text(s,20,95,178,"MUTED",f28,RED);text(s,200,108,99,m.current.available?fmt("%u%% stored",m.current.volume):"--",f12,DIM,LV_TEXT_ALIGN_RIGHT);}
    else{text(s,20,92,133,volume(m.current),f36,INK);text(s,140,111,28,"%",f14,DIM);text(s,207,111,92,"VOLUME",f12,DIM,LV_TEXT_ALIGN_RIGHT);}
    bar(s,20,138,280,8,m.current.volume,TRACK,m.current.muted?MUTED:CYAN,4);
    if(m.mode==3){text(s,20,155,280,mediaStatus(),f12,DIM);text(s,20,173,280,mediaTitle(),vn14,INK);}
    else{text(s,20,166,60,"SIGNAL",f12,DIM);bar(s,82,169,218,4,m.meterCurrent,TRACK,CYAN,2);}}
void select(lv_obj_t* s){shell(s,selectTitle());for(int i=0;i<3;i++){int y=36+i*53;const auto& a=slot(i);
    box(s,8,y,304,48,i==1?SELECTED:SURFACE,6);if(i==1)box(s,8,y+8,3,32,CYAN,1);
    text(s,20,y+5,221,name(a),vn14,INK);text(s,247,y+7,53,volume(a,true),f16,i==1?CYAN:DIM,LV_TEXT_ALIGN_RIGHT);
    text(s,20,y+29,279,role(a,i==1),f12,i==1?CYAN:DIM);}}
void game(lv_obj_t* s){shell(s,"GAME MIXER");for(int i=0;i<2;i++){int x=8+i*160;const auto& a=i?m.current:m.alternate;
    box(s,x,36,152,156,i?SURFACE:SELECTED,8);text(s,x+12,48,128,i?"CHANNEL B":"CHANNEL A",f14,i?DIM:CYAN);
    text(s,x+12,75,128,name(a),vn14,INK);text(s,x+12,105,105,volume(a),f36,INK);text(s,x+116,126,24,"%",f12,DIM);
    bar(s,x+12,149,128,8,a.volume,TRACK,a.muted?MUTED:i?DIM:CYAN,4);
    text(s,x+12,171,128,a.muted?"MUTED":i?"READY":"ADJUSTING",f12,a.muted?RED:i?DIM:CYAN);}}
void health(lv_obj_t* s){shell(s,"PC STATUS");const char* names[]={"CPU","GPU","RAM"};unsigned vals[]={m.cpu,m.gpu,m.ram};
    for(int i=0;i<3;i++){int y=35+i*37;box(s,8,y,304,33,SURFACE,6);text(s,20,y+4,48,names[i],f14,INK);
        text(s,79,y+5,141,i==2?ramInfo():temp(i?m.gpuTemp:m.cpuTemp),f12,DIM);
        text(s,227,y+2,72,stats(vals[i]),f20,INK,LV_TEXT_ALIGN_RIGHT);bar(s,20,y+27,280,3,m.statsValid?vals[i]:0,TRACK,CYAN,1);}
    text(s,12,154,296,netBoth(),f12,DIM);text(s,12,178,296,debugInfo(),f12,DIM);}
void offline(lv_obj_t* s){reset(s,BG);logo(s,136,37,true);text(s,12,110,296,"Waiting for PC",f24,INK,LV_TEXT_ALIGN_CENTER);
    text(s,12,153,296,"Open VuNMix on your computer",f14,DIM,LV_TEXT_ALIGN_CENTER);text(s,12,202,296,"PC LINK OFFLINE",f12,DIM,LV_TEXT_ALIGN_CENTER);}
void draw(lv_obj_t* s){switch(m.page){case Page::Audio:audio(s);break;case Page::Select:select(s);break;
    case Page::Game:game(s);break;case Page::Health:health(s);break;case Page::Offline:offline(s);break;}}
}
