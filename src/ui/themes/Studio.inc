namespace studio {
using namespace v;
constexpr uint32_t BG=0x1D201D,INK=0xEFE8D8,DIM=0xA5A99F,RULE=0x454A41,AMBER=0xE9B45B,FACE=0xE7DEC7,BLACK=0x262B24,NEEDLE=0xB96022;
void shell(lv_obj_t* s,bool online=true){reset(s,BG);logo(s,10,7);text(s,38,8,174,"VU / STUDIO",f14,INK);
    text(s,235,9,62,online?"PC LINK":"PC OFF",f12,DIM,LV_TEXT_ALIGN_RIGHT);box(s,303,14,5,5,online?AMBER:RULE,2);box(s,12,32,296,1,RULE);
    const char* modes[]={"OUT","IN","APPS","MIX","PC"};for(int i=0;i<5;i++){bool active=online&&i==m.mode-1;
        text(s,12+i*60,41,56,modes[i],f12,active?AMBER:DIM,LV_TEXT_ALIGN_CENTER);if(active)box(s,27+i*60,58,26,2,AMBER);}}
void segments(lv_obj_t* s,int x,int y,int count,int w,int h,int gap,int val,uint32_t ink=AMBER){
    int on=(clamp(val)*count+50)/100;for(int i=0;i<count;i++)box(s,x+i*(w+gap),y,w,h,i<on?ink:RULE);}
void gauge(lv_obj_t* s){box(s,10,67,300,108,FACE,2);text(s,18,74,98,m.current.muted?"STORED %":"VOLUME %",f12,BLACK);
    if(m.current.muted)text(s,237,75,65,"MUTED",f12,NEEDLE,LV_TEXT_ALIGN_RIGHT);
    constexpr int cx=139,cy=164;constexpr double pi=3.141592653589793;
    auto px=[&](double a,int r){return cx+int(std::lround(std::cos(a*pi/180)*r));};
    auto py=[&](double a,int r){return cy+int(std::lround(std::sin(a*pi/180)*r));};
    for(int i=0;i<=20;i++){double a=200+i*7.0;line(s,px(a,56),py(a,56),px(a,i%5?51:45),py(a,i%5?51:45),BLACK,i%5?1:2);
        if(i<20)line(s,px(a,58),py(a,58),px(a+7,58),py(a+7,58),0xA7A18F);
        if(i%5==0)text(s,px(a,75)-18,py(a,75)-8,36,fmt("%u",i*5),f12,BLACK,LV_TEXT_ALIGN_CENTER);}
    double angle=200+clamp(m.current.volume)*1.4;line(s,cx,cy,px(angle,53),py(angle,53),m.current.muted?0x8B897F:NEEDLE,3);
    box(s,cx-6,cy-6,12,12,BLACK,6);box(s,cx-2,cy-2,4,4,FACE,2);
    text(s,230,110,74,volume(m.current),f36,BLACK,LV_TEXT_ALIGN_RIGHT);text(s,272,151,29,"%",f12,BLACK,LV_TEXT_ALIGN_RIGHT);}
void audio(lv_obj_t* s){shell(s,m.pcConnected);gauge(s);text(s,12,m.mode==3?177:183,223,name(m.current),vn14,INK);
    if(m.mode==3){text(s,12,200,296,mediaStatus(),f12,AMBER);text(s,12,218,296,mediaTitle(),vn14,INK);}
    else{text(s,239,187,69,m.current.isDefault?"DEFAULT":"DEVICE",f12,AMBER,LV_TEXT_ALIGN_RIGHT);
        text(s,12,216,65,"SIGNAL",f12,DIM);segments(s,83,218,18,7,7,2,m.meterCurrent);
        text(s,252,216,56,fmt("%u%%",m.meterCurrent),f12,INK,LV_TEXT_ALIGN_RIGHT);}}
void select(lv_obj_t* s){shell(s,m.pcConnected);text(s,12,68,296,selectTitle(),f12,DIM);
    for(int i=0;i<3;i++){const auto& a=slot(i);int y=89+i*43;
        if(i==1){box(s,10,y-2,300,43,0x34382E);box(s,10,y-2,3,43,AMBER);}else box(s,12,y-3,296,1,RULE);
        text(s,17,y+5,23,i==0?"<":i==1?">":"+",f12,DIM);text(s,45,y,195,name(a),vn14,INK);
        text(s,246,y+1,47,volume(a),f24,i==1?AMBER:INK,LV_TEXT_ALIGN_RIGHT);text(s,295,y+10,13,"%",f12,DIM);
        text(s,45,y+23,189,role(a,i==1),f12,i==1?AMBER:DIM);}
    text(s,12,223,296,"Previous / selected / next",f12,DIM);}
void game(lv_obj_t* s){shell(s,m.pcConnected);box(s,159,70,1,163,RULE);
    for(int i=0;i<2;i++){const auto& a=i?m.current:m.alternate;int x=12+i*164;
        text(s,x,70,136,i?"CH B":"CH A / TARGET",f12,i?DIM:AMBER);text(s,x,91,136,name(a),vn14,INK);
        text(s,x,120,113,volume(a),f48,i?INK:AMBER);text(s,x+88,178,27,"%",f12,DIM);
        for(int j=0;j<12;j++)box(s,x+124,192-j*7,12,5,j<(clamp(a.volume)*12+50)/100?(i?INK:AMBER):RULE);
        text(s,x,183,87,a.muted?"MUTED":"VOLUME",f12,a.muted?AMBER:DIM);box(s,x,210,136,i?1:2,i?RULE:AMBER);
        text(s,x,221,136,i?"CHANNEL B":"ADJUSTING A",f12,i?DIM:AMBER);}}
void health(lv_obj_t* s){shell(s,m.pcConnected);const char* names[]={"CPU","GPU","RAM"};unsigned vals[]={m.cpu,m.gpu,m.ram};
    for(int i=0;i<3;i++){int y=69+i*45;text(s,12,y,46,names[i],f16,INK);text(s,65,y+2,144,i==2?ramInfo():temp(i?m.gpuTemp:m.cpuTemp),f12,DIM);
        text(s,225,y-3,83,stats(vals[i]),f24,AMBER,LV_TEXT_ALIGN_RIGHT);segments(s,12,y+25,20,12,6,3,m.statsValid?vals[i]:0);}
    text(s,12,203,296,netBoth(),f12,INK);text(s,12,224,296,debugInfo(),f12,DIM);}
void offline(lv_obj_t* s){shell(s,false);logo(s,136,77,true);text(s,12,142,296,"Waiting for PC",f20,INK,LV_TEXT_ALIGN_CENTER);
    text(s,12,174,296,"Open VuNMix on your computer",f12,DIM,LV_TEXT_ALIGN_CENTER);box(s,12,209,296,1,RULE);
    text(s,12,220,296,"PC LINK OFFLINE",f12,AMBER,LV_TEXT_ALIGN_CENTER);}
void draw(lv_obj_t* s){switch(m.page){case Page::Audio:audio(s);break;case Page::Select:select(s);break;
    case Page::Game:game(s);break;case Page::Health:health(s);break;case Page::Offline:offline(s);break;}}
}
