namespace blocks {
using namespace v;
constexpr uint32_t CREAM=0xF5EEDC,BLUE=0x2349DB,ORANGE=0xF78C46,INK=0x172031,BLUE_TRACK=0x526FDF,SUB=0x50545C;
void pc(lv_obj_t* s){text(s,218,17,42,"PC",f12,INK);box(s,245,20,6,6,m.pcConnected?BLUE:SUB,3);logo(s,283,12);}
void index(lv_obj_t* s){text(s,218,151,88,fmt("0%u / 05",m.mode),f14,INK);
    for(int i=0;i<5;i++)box(s,218+i*18,176,13,4,i==m.mode-1?BLUE:0xD8D2C4);}
void audio(lv_obj_t* s){
    bool muted=m.current.muted;reset(s,CREAM);
    if(m.mode==3){box(s,196,0,124,240,BLUE);box(s,0,152,196,88,ORANGE);
        text(s,14,16,172,name(m.current),vn14,INK);text(s,14,61,164,LV_SYMBOL_AUDIO,f20,BLUE);
        text(s,14,99,172,mediaTitle(),vn14,INK);text(s,14,168,172,mediaStatus(),f12,INK);text(s,12,187,178,"MEDIA",f36,INK);
        logo(s,283,12);text(s,204,73,108,volume(m.current),f48,CREAM,LV_TEXT_ALIGN_CENTER);
        text(s,206,132,104,"%",f20,CREAM,LV_TEXT_ALIGN_CENTER);
        text(s,206,165,104,muted?"MUTED":"VOLUME",f12,CREAM,LV_TEXT_ALIGN_CENTER);
        text(s,210,218,102,"03 / 05",f12,CREAM,LV_TEXT_ALIGN_CENTER);return;}
    box(s,0,0,204,188,muted?ORANGE:BLUE);box(s,0,188,320,52,muted?BLUE:ORANGE);pc(s);
    text(s,14,16,178,modeName(),f16,muted?INK:CREAM);
    if(muted){text(s,13,61,182,"MUTED",f36,INK);text(s,14,115,176,volume(m.current,true),f28,INK);
        text(s,14,153,176,"STORED LEVEL",f12,INK);
    }else{text(s,12,56,137,volume(m.current),f48,CREAM);text(s,155,91,37,"%",f20,CREAM);
        text(s,14,124,175,"VOLUME",f12,CREAM);bar(s,14,156,174,12,m.current.volume,BLUE_TRACK,CREAM);}
    text(s,218,59,90,"SIGNAL",f12,SUB);text(s,215,83,94,fmt("%u%%",m.meterCurrent),f28,INK);
    bar(s,218,124,87,6,m.meterCurrent,0xD8D2C4,BLUE);index(s);
    text(s,14,196,293,name(m.current),vn14,muted?CREAM:INK);
    text(s,14,222,291,m.current.isDefault?"DEFAULT DEVICE":"DEVICE VOLUME",f12,muted?CREAM:INK);
}
void select(lv_obj_t* s){reset(s,CREAM);box(s,0,74,320,80,ORANGE);box(s,0,154,320,86,BLUE);
    text(s,14,8,258,selectTitle(),f12,INK);logo(s,288,8);
    for(int i=0;i<3;i++){const auto& a=slot(i);int y=i==0?29:i==1?88:169;uint32_t ink=i==2?CREAM:INK;
        text(s,14,y,204,name(a),vn14,ink);text(s,14,y+(i==0?26:31),208,role(a,i==1),f12,ink);
        text(s,226,y-1,82,volume(a),i==0?f24:f48,ink,LV_TEXT_ALIGN_RIGHT);
        if(i)text(s,291,y+47,20,"%",f12,ink,LV_TEXT_ALIGN_RIGHT);}
}
void game(lv_obj_t* s){reset(s,BLUE);box(s,196,0,124,240,ORANGE);
    text(s,14,14,172,"CHANNEL A",f14,CREAM);text(s,210,14,74,"CH. B",f14,INK);logo(s,287,12);
    text(s,14,61,172,name(m.alternate),vn14,CREAM);text(s,210,61,100,name(m.current),vn14,INK);
    text(s,12,101,145,volume(m.alternate),f48,CREAM);text(s,158,135,30,"%",f16,CREAM);
    text(s,207,101,103,volume(m.current),f48,INK);text(s,285,158,23,"%",f12,INK,LV_TEXT_ALIGN_RIGHT);
    bar(s,14,171,167,10,m.alternate.volume,BLUE_TRACK,CREAM);bar(s,210,181,96,8,m.current.volume,0xE8B18A,INK);
    box(s,14,205,109,23,CREAM);text(s,21,209,97,m.alternate.muted?"MUTED / A":"ADJUSTING",f12,BLUE);
    text(s,210,210,96,m.current.muted?"MUTED / B":"READY",f12,INK);
}
void health(lv_obj_t* s){reset(s,CREAM);box(s,0,0,160,140,BLUE);box(s,160,0,160,140,ORANGE);
    text(s,14,14,101,"CPU",f16,CREAM);logo(s,127,12);text(s,174,14,131,"GPU",f16,INK);
    text(s,12,51,112,stats(m.cpu,false),f48,CREAM);text(s,128,94,20,"%",f12,CREAM);
    text(s,173,51,112,stats(m.gpu,false),f48,INK);text(s,290,94,20,"%",f12,INK);
    text(s,14,116,132,temp(m.cpuTemp),f14,CREAM);text(s,174,116,131,temp(m.gpuTemp),f14,INK);
    text(s,14,150,95,"RAM",f14,INK);text(s,12,173,105,stats(m.ram),f28,INK);
    text(s,118,149,185,ramInfo(),f14,SUB);text(s,118,178,62,"DOWN",f12,SUB);text(s,194,176,112,net(false),f16,INK);
    text(s,118,201,62,"UP",f12,SUB);text(s,194,199,112,net(true),f16,INK);text(s,14,224,294,debugInfo(),f12,SUB);
}
void offline(lv_obj_t* s){reset(s,CREAM);box(s,0,0,96,240,ORANGE);box(s,96,104,224,136,BLUE);
    logo(s,24,24,true);text(s,24,128,48,"!",f48,INK,LV_TEXT_ALIGN_CENTER);text(s,112,24,193,"PC LINK",f14,INK);
    text(s,110,52,197,"OFFLINE",f28,INK);text(s,112,124,194,"Waiting for PC",f20,CREAM);
    text(s,112,173,194,"Open VuNMix",f14,CREAM);text(s,112,196,194,"on your computer",f14,CREAM);}
void draw(lv_obj_t* s){switch(m.page){case Page::Audio:audio(s);break;case Page::Select:select(s);break;
    case Page::Game:game(s);break;case Page::Health:health(s);break;case Page::Offline:offline(s);break;}}
}
