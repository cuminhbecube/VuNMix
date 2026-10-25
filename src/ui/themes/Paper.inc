namespace paper {
using namespace v;
constexpr uint32_t PAGE=0xF2EEE1,BLACK=0x191B18,DIM=0x66665C,RULE=0xB8B7A9,RED=0xC9452C;
void sheet(lv_obj_t* s,const char* title,bool offline=false){reset(s,PAGE);box(s,12,8,296,3,RED);
    text(s,12,23,43,fmt("0%u",offline?0:m.mode),f28,BLACK);
    const char* modes[]={"LINK","OUT","IN","APP","MIX","PC"};text(s,12,61,43,modes[offline?0:m.mode],f12,BLACK);
    box(s,58,22,1,194,BLACK);text(s,72,23,236,title,f20,BLACK);logo(s,22,189);}
void rule(lv_obj_t* s,int y,uint32_t color=RULE,int h=1){box(s,72,y,236,h,color);}
void mixline(lv_obj_t* s,int x,int y,int w,int val,uint32_t ink=RED){box(s,x,y,w,2,RULE);box(s,x,y,w*clamp(val)/100,3,ink);}
void audio(lv_obj_t* s){sheet(s,modeName());text(s,72,52,236,currentRole(),f12,m.current.muted?RED:DIM);
    text(s,72,77,236,name(m.current),vn14,BLACK);text(s,70,106,120,volume(m.current),f48,BLACK);
    text(s,183,139,28,"%",f20,BLACK);text(s,215,141,93,m.current.muted?"STORED":"VOLUME",f12,m.current.muted?RED:DIM,LV_TEXT_ALIGN_RIGHT);
    mixline(s,72,174,236,m.current.volume,m.current.muted?DIM:RED);
    if(m.mode==3){text(s,72,187,236,mediaStatus(),f12,RED);text(s,72,210,236,mediaTitle(),vn14,BLACK);}
    else{text(s,72,183,48,"0",f12,DIM);text(s,263,183,45,"100",f12,DIM,LV_TEXT_ALIGN_RIGHT);rule(s,207);
        text(s,72,217,134,fmt("SIGNAL %u%%",m.meterCurrent),f12,BLACK);text(s,212,217,96,m.pcConnected?"PC ONLINE":"PC OFFLINE",f12,DIM,LV_TEXT_ALIGN_RIGHT);}}
void select(lv_obj_t* s){sheet(s,m.mode==4?(m.selectChannel=='B'?"Choose B":"Choose A"):m.mode==3?"Applications":m.mode==2?"Choose input":"Choose output");
    for(int i=0;i<3;i++){const auto& a=slot(i);int y=65+i*51;
        text(s,72,y,173,name(a),vn14,BLACK);text(s,249,y+2,59,volume(a,true),f16,i==1?RED:BLACK,LV_TEXT_ALIGN_RIGHT);
        text(s,72,y+23,236,role(a,i==1),f12,i==1?RED:DIM);if(i==1)box(s,65,y-1,3,43,RED);if(i<2)rule(s,y+42);}
    text(s,72,222,236,"Previous / selected / next",f12,DIM);}
void game(lv_obj_t* s){sheet(s,"Game mix");text(s,72,52,236,"ADJUSTING CHANNEL A",f12,RED);
    for(int i=0;i<2;i++){const auto& a=i?m.current:m.alternate;int y=84+i*80;
        text(s,72,y,40,i?"B":"A",f36,i?BLACK:RED);text(s,115,y,193,name(a),vn14,BLACK);
        text(s,115,y+28,92,a.muted?"MUTED":"VOLUME",f12,a.muted?RED:DIM);
        text(s,211,y+25,97,volume(a,true),f28,i?BLACK:RED,LV_TEXT_ALIGN_RIGHT);mixline(s,115,y+58,193,a.volume,i?BLACK:RED);}}
void health(lv_obj_t* s){sheet(s,"System");text(s,72,52,236,"PC TELEMETRY",f12,DIM);
    const char* labels[]={"CPU","GPU","RAM"};unsigned values[]={m.cpu,m.gpu,m.ram};
    for(int i=0;i<3;i++){int y=78+i*40;rule(s,y-9);text(s,72,y,49,labels[i],f16,BLACK);
        text(s,126,y+3,91,i==2?ramInfo():temp(i?m.gpuTemp:m.cpuTemp),f12,DIM);
        text(s,221,y-3,87,stats(values[i]),f28,BLACK,LV_TEXT_ALIGN_RIGHT);}
    rule(s,192,BLACK);text(s,72,201,236,netBoth(),f12,RED);text(s,72,223,236,debugInfo(),f12,DIM);}
void offline(lv_obj_t* s){sheet(s,"Disconnected",true);text(s,72,54,236,"PC LINK OFFLINE",f12,RED);
    logo(s,72,80,true);text(s,72,142,236,"Waiting for PC",f24,BLACK);text(s,72,182,236,"Open VuNMix on",f14,DIM);
    text(s,72,202,236,"your computer",f14,DIM);rule(s,228,RED,3);}
void draw(lv_obj_t* s){switch(m.page){case Page::Audio:audio(s);break;case Page::Select:select(s);break;
    case Page::Game:game(s);break;case Page::Health:health(s);break;case Page::Offline:offline(s);break;}}
}
