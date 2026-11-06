"""Trusted one-off manual annotation for the two generated Akino key poses.
Coordinates refer to the original 1122 x 1402 images; no automatic recognition.
"""
import json
from pathlib import Path

# name: (pose A x,y, pose B x,y). Left/right mean IMAGE side.
P = {
 'hair_top':(520,96,510,97), 'hair_left':(270,445,243,455),
 'hair_right':(847,445,793,410), 'hair_bottom_l':(390,558,365,558),
 'hair_bottom_r':(735,548,707,539), 'hair_peak_l':(363,180,348,184),
 'hair_peak_r':(722,178,677,160), 'hair_low_l':(295,511,277,529),
 'hair_low_r':(810,512,757,499), 'ahoge_root':(526,112,480,112),
 'ahoge_tip':(680,76,616,67), 'ahoge_top':(575,20,520,16),
 'star':(390,265,380,263), 'bang_tip':(567,385,570,366),
 'bang_left':(420,356,420,347), 'bang_right':(662,310,656,298),
 'eye_l':(477,412,483,397), 'eye_r':(636,397,634,369),
 'eye_l_outer':(408,417,422,402),'eye_l_inner':(510,419,518,403),
 'eye_l_top':(475,369,480,357),'eye_l_bottom':(481,455,491,442),
 'eye_r_inner':(606,396,610,375),'eye_r_outer':(696,387,691,361),
 'eye_r_top':(631,346,629,325),'eye_r_bottom':(635,434,640,410),
 'nose':(552,445,588,426),'mouth':(565,491,582,473),
 'mouth_l':(532,474,551,459),'mouth_r':(597,469,612,449),
 'mouth_bottom':(568,518,586,501),'chin':(553,543,570,527),
 'face_l':(421,478,438,470),'face_r':(701,456,696,435),
 'neck':(565,554,573,539), 'shoulder_l':(452,587,481,568),
 'shoulder_r':(646,590,663,571),'elbow_l':(395,679,452,705),
 'elbow_r':(715,743,737,614),'wrist_l':(320,592,524,666),
 'wrist_r':(770,831,806,522),'palm_l':(307,553,533,624),
 'palm_r':(799,846,845,483),'finger_l_top':(291,491,542,584),
 'finger_l_outer':(244,548,509,619),'finger_l_inner':(358,530,562,617),
 'finger_l_bottom':(305,605,525,674),
 'finger_r_top':(825,827,835,432),'finger_r_outer':(859,837,925,475),
 'finger_r_inner':(766,850,805,489),'finger_r_bottom':(797,887,827,529),
 'sleeve_l_outer':(291,627,408,710),'sleeve_l_bottom':(390,720,456,758),
 'sleeve_r_outer':(798,802,847,546),'sleeve_r_bottom':(733,855,791,616),
 'waist':(523,850,613,816),'hip_l':(431,877,530,836),
 'hip_r':(571,883,652,840),'coat_l_mid':(359,818,415,798),
 'coat_r_mid':(669,824,738,792),'coat_l_outer':(305,945,358,903),
 'coat_l_bottom':(377,1004,485,977),'coat_r_outer':(720,976,795,910),
 'coat_r_bottom':(600,1020,724,966),
 'badge_top_l':(464,745,583,712),'badge_top_r':(553,755,664,705),
 'badge_bottom_l':(447,855,592,819),'badge_bottom_r':(543,867,677,814),
 'knee_l':(458,1083,465,1054),'knee_r':(606,1080,622,1056),
 'ankle_l':(464,1264,413,1225),'ankle_r':(664,1218,608,1221),
 'shoe_l_left':(424,1302,365,1252),'shoe_l_right':(516,1300,463,1263),
 'shoe_l_bottom':(468,1350,411,1318),'shoe_r_left':(626,1280,562,1256),
 'shoe_r_right':(718,1220,674,1263),'shoe_r_bottom':(665,1320,622,1297),
 'leg_l_outer':(403,1140,401,1121),'leg_l_inner':(520,1140,532,1122),
 'leg_r_outer':(697,1153,662,1138),'leg_r_inner':(567,1163,562,1138),
}
# Global fixed anchors keep the exterior background still.
for i,(x,y) in enumerate([(0,0),(561,0),(1121,0),(1121,700),(1121,1401),(561,1401),(0,1401),(0,700)]):
 P[f'border_{i}']=(x,y,x,y)
BONES=[['neck','shoulder_l','elbow_l','wrist_l','palm_l'],['neck','shoulder_r','elbow_r','wrist_r','palm_r'],['neck','waist','hip_l','knee_l','ankle_l'],['waist','hip_r','knee_r','ankle_r'],['eye_l','eye_r'],['shoulder_l','shoulder_r'],['hip_l','hip_r']]
if __name__=='__main__':
 data={'schema_version':1,'annotation':'manual visual estimates by Misaki; not automatically detected','size':[1122,1402], 'points':{n:{'a':list(v[:2]),'b':list(v[2:])} for n,v in P.items()},'bones':BONES}
 Path(__file__).with_name('akino_landmarks.json').write_text(json.dumps(data,indent=2)+'\n')
