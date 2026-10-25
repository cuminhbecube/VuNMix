namespace pixel {
using namespace v;
constexpr uint32_t BODY=0x879665,FIELD=0xD0DDA5,INK=0x243C24,SOFT=0x536B42,TRACK=0xABBD84,RULE=0x809761;
void label(lv_obj_t* s,int x,int y,int w,const char* t,const lv_font_t* f=mono,uint32_t ink=INK,lv_text_align_t a=LV_TEXT_ALIGN_LEFT){text(s,x,y,w,t,f,ink,a);}
const char* glyph(char ch){switch(ch){
    case '0':return "01110100011001110101110011000101110";case '1':return "00100011000010000100001000010001110";
    case '2':return "01110100010000100010001000100011111";case '3':return "11110000010000101110000010000111110";
    case '4':return "00010001100101010010111110001000010";case '5':return "11111100001000011110000010000111110";
    case '6':return "01110100001000011110100011000101110";case '7':return "11111000010001000100010000100001000";
    case '8':return "01110100011000101110100011000101110";case '9':return "01110100011000101111000010000101110";
    case 'M':return "10001110111010110101100011000110001";case 'U':return "10001100011000110001100011000101110";
    case 'T':return "11111001000010000100001000010000100";case 'E':return "11111100001000011110100001000011111";
    case '-':return "00000000000000011111000000000000000";default:return "00000000000000000000000000000000000";}}
void digits(lv_obj_t* s,int x,int y,const char* value,int unit){for(const char* p=value;*p;p++){const char* bits=glyph(*p);
    for(int row=0;row<7;row++)for(int col=0;col<5;){if(bits[row*5+col]!='1'){col++;continue;}int begin=col;
        while(col<5&&bits[row*5+col]=='1')col++;box(s,x+begin*unit,y+row*unit,(col-begin)*unit,unit,INK);}x+=6*unit;}}
void segments(lv_obj_t* s,int x,int y,int w,int h,int value,int count=20){int active=(clamp(value)*count+50)/100;
    for(int i=0;i<count;i++){int a=x+w*i/count,b=x+w*(i+1)/count;box(s,a,y,b-a-2,h,i<active?INK:TRACK);}}
void base(lv_obj_t* s,const char* title,bool online=true){reset(s,BODY);box(s,6,6,50,228,INK);logo(s,21,14);
    const char* modes[]={"OUT","IN","APP","MIX","PC"};for(int i=0;i<5;i++){int y=46+i*36;bool active=online&&i==m.mode-1;
        if(active){box(s,10,y,42,29,FIELD);box(s,52,y+10,4,9,FIELD);}label(s,10,y+7,42,modes[i],f12,active?INK:FIELD,LV_TEXT_ALIGN_CENTER);}
    box(s,62,6,252,228,INK);box(s,66,10,244,220,FIELD);for(auto x:{62,310})for(auto y:{6,230})box(s,x,y,4,4,BODY);
    label(s,76,20,168,title);label(s,248,20,48,online?"USB":"OFF",mono,SOFT,LV_TEXT_ALIGN_RIGHT);box(s,76,43,220,2,RULE);}
void audio(lv_obj_t* s){bool muted=m.current.muted;base(s,m.mode==3?"APP":m.mode==2?"INPUT":"OUTPUT",m.pcConnected);
    label(s,76,54,220,name(m.current),vn14);label(s,76,76,220,currentRole(),f12,SOFT);
    if(muted){digits(s,88,105,"MUTE",6);label(s,76,157,220,m.current.available?fmt("%u%% STORED",m.current.volume):"-- STORED",mono,SOFT,LV_TEXT_ALIGN_CENTER);}
    else{digits(s,88,103,volume(m.current),8);label(s,240,143,32,"%");label(s,248,114,48,"VOL",mono,SOFT);}
    if(m.mode==3){segments(s,76,168,220,9,m.current.volume);label(s,76,186,220,mediaStatus(),f12,SOFT);label(s,76,207,220,mediaTitle(),vn14);}
    else{segments(s,76,181,220,11,m.current.volume);label(s,76,208,66,fmt("SIG %u%%",m.meterCurrent),f12,SOFT);segments(s,146,210,150,8,m.meterCurrent,16);}}
void select(lv_obj_t* s){base(s,m.mode==4?(m.selectChannel=='B'?"SELECT B":"SELECT A"):"BROWSE",m.pcConnected);
    for(int i=0;i<3;i++){const auto& a=slot(i);int y=54+45*i;bool focused=i==1;if(focused)box(s,72,y,228,42,INK);
        label(s,80,y+3,158,name(a),vn14,focused?FIELD:INK);label(s,244,y+5,48,volume(a,true),f14,focused?FIELD:INK,LV_TEXT_ALIGN_RIGHT);
        label(s,80,y+25,212,role(a,focused),f12,focused?FIELD:SOFT);if(!focused)box(s,76,y+42,220,1,RULE);}
    label(s,76,205,220,"Previous / selected / next",f12,INK,LV_TEXT_ALIGN_CENTER);}
void game(lv_obj_t* s){base(s,"GAME MIX",m.pcConnected);label(s,76,55,144,"GAME A");label(s,232,55,64,volume(m.alternate,true));
    label(s,76,79,220,name(m.alternate),vn14);segments(s,76,104,220,12,m.alternate.volume);
    label(s,76,124,220,m.alternate.muted?"MUTED / ADJUSTING A":"ADJUSTING CHANNEL A",f12,SOFT);box(s,76,147,220,2,RULE);
    label(s,76,159,144,m.current.muted?"B MUTED":"VOICE B");label(s,232,159,64,volume(m.current,true));
    label(s,76,182,220,name(m.current),vn14);segments(s,76,207,220,12,m.current.volume);}
void health(lv_obj_t* s){base(s,"PC DATA",m.pcConnected);const char* names[]={"CPU","GPU","RAM"};unsigned vals[]={m.cpu,m.gpu,m.ram};
    for(int i=0;i<3;i++){int y=53+i*42;label(s,76,y,48,names[i]);label(s,232,y,64,stats(vals[i]));
        label(s,134,y+2,96,i==2?ramInfo():temp(i?m.gpuTemp:m.cpuTemp),f12,SOFT,LV_TEXT_ALIGN_CENTER);segments(s,76,y+25,220,7,m.statsValid?vals[i]:0);}
    label(s,76,186,220,netBoth(),f12,INK);label(s,76,211,220,debugInfo(),f12,SOFT);}
void offline(lv_obj_t* s){base(s,"VUNMIX",false);logo(s,162,57,true);label(s,72,122,232,"WAITING FOR PC",mono,INK,LV_TEXT_ALIGN_CENTER);
    label(s,76,157,220,"Open VuNMix on",f14,SOFT,LV_TEXT_ALIGN_CENTER);label(s,76,178,220,"your computer",f14,SOFT,LV_TEXT_ALIGN_CENTER);
    label(s,76,209,220,"PC LINK OFFLINE",f12,INK,LV_TEXT_ALIGN_CENTER);}
void draw(lv_obj_t* s){switch(m.page){case Page::Audio:audio(s);break;case Page::Select:select(s);break;
    case Page::Game:game(s);break;case Page::Health:health(s);break;case Page::Offline:offline(s);break;}}
}
