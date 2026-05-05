# analytics, calculator agent 디자인

## analytics

1. 분석 에이전트의 목적
 회귀모델을 통해 예측된 캐릭터의 기대 전투력을 기반으로 실제 전투력을 비교하여 실제로 현재 스펙이 효율적인지를 판단하고
 그것을 기반으로 무엇으로 인해 병목현상이 발생했는가를 판단하는 에이전트를 개발한다.

2. 분석 에이전트의 툴
 1) 기대 전투력 판단 툴
 작동 로직: 학습된 회귀 모델을 실행하여 해당 직업군에서 이 정도 내실을 갖췄을 때 나와야 하는 표준 전투력($Expected CP$)을 산출합니다.
 
 역할: 캐릭터 진단을 위한 '객관적인 기준점'을 제시합니다.


 2) 스펙 효율 진단 툴 (Efficiency Diagnostic Tool)
 기대치와 실제치를 대조하여 현재 세팅의 완성도를 판단하는 툴입니다.<br>

 입력 데이터: 기대 전투력(툴 1의 결과) 및 final_stats.combat_power (Open API 실측 데이터).  

 작동 로직: $Efficiency = \frac{Actual CP}{Expected CP}$  계산된 비율을 통해 기준상 효율이 어느정도인지를 파악한다.<br>

  판단: 고효율-> 내실 대비 장비 세팅이 매우 훌륭함.<br>
          저효율-> 내실에 비해 장비가 부실하거나, 반대로 장비는 좋은데 내실(유니온 등)이 받쳐주지 못함.


 3)  병목 현상 판단 툴 (Bottleneck Identification Tool)효율이 낮을 경우, 구체적으로 어떤 부위나 시스템이 성장을 가로막는지 찾아내는 툴입니다.<br>
 입력 데이터: equipment_list, v_matrix, hexa_core, ability_info 등 캐릭터 전수 데이터.  <br>

 작동 로직:부위별 점수화: 각 장비의 스타포스, 잠재등급 등을 점수화하여 평균보다 현저히 낮은 부위 추출.  

 시스템 대조: 장비 점수는 높은데 효율이 낮다면 스킬 코어(v_matrix)나 유니온(union_info)을 범인으로 지목. 
  
 출력 데이터: GrowthEfficiencyReport의 bottleneck_analysis와 recommended_actions 리스트.

## calculator