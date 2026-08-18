# Bộ câu hỏi benchmark SoulViet Agent — phiên bản 2 (MVP điểm tham quan)

Bộ đề gồm 60 câu tiếng Việt tự nhiên. Mục đích là kiểm tra khả năng hiểu yêu
cầu, tự chọn tool, tạo và chỉnh sửa hành trình, tối ưu di chuyển, duy trì ngữ
cảnh và trả lời trung thực.

Quy ước:

- Các câu ghi **Cần lịch hiện tại** phải được chạy sau khi đã gọi `/plan`.
- Các câu ghi **Nhiều lượt** phải dùng cùng `user_id` và `thread_id`.
- “Không hỏi lại” chỉ áp dụng khi dữ kiện đã đủ để tự lập lịch. Khi thiếu tham
  chiếu thật sự, agent phải hỏi một câu làm rõ ngắn gọn.
- Một ca sửa lịch chỉ đạt khi `committed=true` và
  `validation_report.acceptable=true`, trừ ca được thiết kế để kiểm tra
  clarification hoặc infeasible.
- MVP chưa lập nhà hàng/bữa ăn. Khi gặp phần yêu cầu ăn uống, agent phải gọi
  `report_unsupported_request`, không bịa địa điểm ăn uống và vẫn thực hiện các
  phần tham quan được hỗ trợ trong cùng câu.

## A. Tự lập lịch và hiểu khu vực — 1 đến 10

1. Tôi muốn đi chơi Hội An trong 2 ngày, bạn tự lên lịch giúp tôi, ưu tiên phố cổ, làng nghề và trải nghiệm địa phương.

   Kỳ vọng: tự tạo lịch tập trung tại Hội An; không hỏi ID hoặc bắt người dùng nêu tên từng địa điểm.

2. Cuối tuần này mình chỉ muốn đi quanh Hội An thôi, lịch nhẹ nhàng, ít di chuyển và có một buổi tối dạo phố.

   Kỳ vọng: hiểu “Hội An” là phạm vi địa lý nhỏ hơn Quảng Nam; không chọn điểm xa như Mỹ Sơn hoặc Tam Kỳ nếu không cần.

3. Lên cho tôi lịch 3 ngày ở Đà Nẵng: có biển, thiên nhiên, trải nghiệm địa phương và mỗi ngày đừng quá dày.

   Kỳ vọng: tự chọn địa điểm phù hợp, đủ 3 ngày, không hỏi địa điểm cụ thể.

4. Tôi có 2 ngày ở Huế, muốn tìm hiểu văn hóa và lịch sử nhưng không muốn đi quá nhiều chùa.

   Kỳ vọng: tạo lịch ở Huế; ưu tiên văn hóa/lịch sử và hạn chế tâm linh theo đúng sắc thái “không quá nhiều”.

5. Cho mình một hành trình 4 ngày ở Quảng Nam, ưu tiên biển, thiên nhiên và trải nghiệm của người địa phương, không đi chùa.

   Kỳ vọng: đổi duration/region, lọc tâm linh, không lặp địa điểm và commit lịch hoàn chỉnh.

6. Tôi muốn nghỉ dưỡng 2 ngày quanh Sơn Trà, ngắm biển, đi chậm và ăn hải sản vào buổi tối.

   Kỳ vọng: hiểu locality Sơn Trà, commit phần lịch tham quan gần nhau; đồng thời
   trả `unsupported_requests.capability=meal_planning` cho phần ăn hải sản, không
   bịa quán ăn và không làm cả yêu cầu thất bại.

7. Lập lịch một ngày ở phố cổ Hội An cho gia đình, bắt đầu lúc 9 giờ và kết thúc trước 20 giờ.

   Kỳ vọng: tuân thủ locality và time window; không yêu cầu người dùng cung cấp place ID.

8. Mình muốn đi Đà Nẵng 3 ngày nhưng chủ yếu ở khu vực ven biển, hạn chế đi sang phía tây thành phố.

   Kỳ vọng: ưu tiên cụm ven biển và phản ánh hạn chế địa lý trong candidate pool.

9. Cho tôi chuyến đi 2 ngày ở Quảng Nam với ngân sách tiết kiệm, ưu tiên những trải nghiệm miễn phí hoặc ít tốn phí.

   Kỳ vọng: đổi budget, ưu tiên chi phí thấp và không bịa giá.

10. Tôi chưa biết ở Hội An có gì hay, cứ chọn những nơi đáng đi nhất và xếp thành lịch 2 ngày hợp lý cho tôi.

    Kỳ vọng: tự đề xuất itinerary; tuyệt đối không hỏi “bạn muốn đi địa điểm nào?”.

## B. Thêm địa điểm, hoạt động và yêu cầu ngoài phạm vi — 11 đến 20

Tất cả câu trong nhóm này **cần lịch hiện tại**.

11. Thêm Chùa Linh Ứng vào ngày 2 của lịch trình.

    Kỳ vọng: resolve tên thành ID thật, ghim đúng ngày 2 và commit.

12. Thêm Bà Nà Hills vào ngày có nhiều thời gian trống nhất.

    Kỳ vọng: tự xác định ngày ít điểm/ít tải nhất, không hỏi người dùng chọn ngày.

13. Ngày 1 thêm giúp mình một bãi biển đẹp, nổi tiếng và tiện đường với các điểm đã có.

    Kỳ vọng: tự tìm candidate biển, ưu tiên chất lượng và chi phí đường đi.

14. Buổi tối ngày 2 cho mình một quán ăn đặc sản Quảng Nam gần tuyến trong ngày.

    Kỳ vọng: không sửa lịch, `committed=false`, trả đúng capability
    `meal_planning`, lý do MVP chỉ có dữ liệu điểm tham quan và không bịa tên quán.

15. Thêm một quán cà phê yên tĩnh vào khoảng giữa buổi chiều ngày 1.

    Kỳ vọng: ghi nhận phần yêu cầu qua `report_unsupported_request`, không tạo
    `cafe_break`, không thay đổi lịch hiện tại.

16. Ngày 3 đang khá trống, hãy tự bổ sung một trải nghiệm ngoài trời phù hợp.

    Kỳ vọng: thêm đúng ngày, category outdoor, không phá distance/time constraints.

17. Tôi muốn có ít nhất hai hoạt động trải nghiệm thực tế trong toàn chuyến đi.

    Kỳ vọng: tạo category constraint `interactive` với `min_count=2`.

18. Thêm một điểm văn hóa vào ngày 2 nhưng đừng thêm chùa hoặc địa điểm tâm linh.

    Kỳ vọng: tự tìm điểm văn hóa phi tâm linh và ghim đúng ngày.

19. Cho mình thêm một chỗ ăn hải sản vào tối nay, chỗ nào gần điểm cuối ngày nhất thì chọn.

    Kỳ vọng: báo chưa hỗ trợ meal planning; không cần hỏi làm rõ “tối nay” vì
    capability này chưa được MVP thực thi, không bịa quán hoặc khoảng cách.

20. Tôi muốn ghé Cầu Rồng nhưng không quan trọng ngày nào, bạn đặt vào ngày tiện đường nhất nhé.

    Kỳ vọng: resolve địa điểm và tự chọn ngày có route cost thấp nhất.

## C. Xóa và loại trừ — 21 đến 30

Tất cả câu trong nhóm này **cần lịch hiện tại**.

21. Bỏ điểm đầu tiên trong ngày 1.

    Kỳ vọng: xóa đúng attraction đầu tiên và commit lịch mới.

22. Xóa điểm thứ 2 trong ngày 2.

    Kỳ vọng: hiểu vị trí đếm từ 1 và xóa đúng mục.

23. Bỏ điểm cuối cùng của ngày 3.

    Kỳ vọng: xóa đúng attraction cuối cùng trong ngày 3.

24. Tôi không muốn đi Bà Nà Hills nữa, bỏ địa điểm này khỏi lịch trình.

    Kỳ vọng: resolve theo tên, loại khỏi toàn chuyến và không tự thêm lại khi replan.

25. Bỏ tất cả chùa và địa điểm tâm linh nhưng giữ lại bảo tàng, di tích lịch sử và các điểm văn hóa.

    Kỳ vọng: lọc đúng tâm linh, không loại nhầm toàn bộ văn hóa/lịch sử.

26. Loại bỏ tất cả các điểm mua sắm khỏi lịch trình.

    Kỳ vọng: không còn mall, store, gift shop hoặc shopping attraction.

27. Tôi không thích các điểm tham quan trong nhà, bỏ chúng và bổ sung điểm ngoài trời nếu ngày bị trống.

    Kỳ vọng: loại indoor, thêm outdoor và vẫn commit lịch hợp lệ.

28. Ngày 2 giữ Chùa Linh Ứng nhưng bỏ các địa điểm tâm linh khác trong ngày đó.

    Kỳ vọng: scoped exclusion ngày 2 với Chùa Linh Ứng là ngoại lệ; không áp dụng nhầm cho toàn chuyến.

29. Ngày đầu tiên hơi nặng, bỏ giúp tôi một điểm ít quan trọng nhất.

    Kỳ vọng: dùng score để bỏ điểm ít quan trọng, không bỏ required/locked place.

30. Xóa chỗ đó khỏi lịch trình giúp tôi.

    Kỳ vọng: nếu không có tham chiếu rõ ràng trong hội thoại trước đó thì hỏi làm rõ, không đoán một địa điểm bất kỳ.

## D. Thay thế, sắp xếp và tối ưu đường đi — 31 đến 40

Tất cả câu trong nhóm này **cần lịch hiện tại**.

31. Bỏ Bà Nà Hills và thay bằng một điểm thiên nhiên gần các điểm còn lại trong ngày 2.

    Kỳ vọng: thay đúng ngày, candidate mới thuộc thiên nhiên và giảm/không làm tăng route cost ngày 2.

32. Đổi tất cả các điểm tâm linh sang những điểm văn hóa hoặc thiên nhiên gần đó.

    Kỳ vọng: thay thế theo category, không chỉ xóa khiến lịch bị trống.

33. Giữ nguyên toàn bộ địa điểm, chỉ sắp xếp lại để tổng quãng đường di chuyển ít nhất.

    Kỳ vọng: attraction set trước/sau giống hệt nhau và distance không tăng.

34. Các điểm trong ngày 1 đang cách nhau xa quá, hãy gom lại thành một cụm gần nhau hơn.

    Kỳ vọng: ưu tiên spatial coherence và giảm travel ngày 1.

35. Tối ưu lại cả chuyến để mỗi ngày tập trung vào một khu vực, đừng chạy qua chạy lại giữa các quận.

    Kỳ vọng: phân cụm theo ngày trước khi xếp tuyến.

36. Ngày 2 có khoảng chờ quá dài, hãy sắp lại hoặc thêm một điểm gần đó để lấp khoảng trống.

    Kỳ vọng: giảm idle gap mà không vi phạm opening hours, distance hay max places.

37. Ngày 1 chỉ nên có tối đa 3 điểm tham quan và ưu tiên các điểm gần nhau.

    Kỳ vọng: day policy riêng ngày 1, không giảm giới hạn các ngày khác.

38. Tôi muốn chuyến đi nhẹ nhàng hơn, mỗi ngày đi ít hơn nhưng vẫn giữ các địa điểm nổi bật nhất.

    Kỳ vọng: giảm mật độ, bảo toàn high-value places và travel hợp lý.

39. Thay bảo tàng trong ngày 2 bằng một hoạt động ngoài trời phù hợp với trẻ em.

    Kỳ vọng: nếu có nhiều bảo tàng và không xác định được cái nào thì hỏi làm rõ; nếu chỉ có một thì tự thay.

40. Đổi điểm cuối ngày 1 sang một nơi có thể tham quan buổi tối và nằm gần tuyến hiện tại.

    Kỳ vọng: xét opening hours/evening suitability và road time.

## E. Yêu cầu phức hợp nhiều ràng buộc — 41 đến 50

Tất cả câu trong nhóm này **cần lịch hiện tại**.

41. Bỏ điểm đầu tiên ngày 1, thêm Bà Nà Hills vào ngày 2, bỏ hết chùa trong toàn chuyến và tối ưu lại để di chuyển ít nhất.

    Kỳ vọng: thực hiện đủ bốn vế trong một transaction rồi validate/commit.

42. Đổi chuyến đi thành 3 ngày. Tôi thích biển, thiên nhiên và trải nghiệm địa phương, không thích chùa. Giữ lại những điểm đáng đi nhất và bổ sung điểm mới nếu cần.

    Kỳ vọng: đổi duration, preferences, exclusions, preserve chọn lọc và fill hợp lý.

43. Chuyển toàn bộ lịch trình sang Đà Nẵng trong 3 ngày, ưu tiên biển, thiên nhiên và những địa điểm nổi tiếng, không lặp điểm.

    Kỳ vọng: xóa constraint/anchor sai vùng cũ, đổi toàn bộ candidate pool sang Đà Nẵng.

44. Tôi chỉ đi Quảng Nam trong 2 ngày, không đi địa điểm tâm linh và mỗi ngày tối đa 4 điểm.

    Kỳ vọng: đổi region, duration, exclusion và density đồng thời.

45. Tôi có 5 ngày thay vì 3 ngày. Hãy mở rộng lịch trình, không lặp địa điểm và mỗi ngày tập trung vào một khu vực gần nhau.

    Kỳ vọng: mở rộng đủ 5 ngày, không có ngày trống nếu dữ liệu khả thi và route theo cụm.

46. Rút chuyến đi còn 2 ngày nhưng cố gắng giữ lại các địa điểm nổi bật nhất và giảm tổng thời gian di chuyển.

    Kỳ vọng: lựa chọn lại theo utility + route cost, không chỉ cắt bỏ ngày cuối.

47. Ngày 1 ưu tiên biển, ngày 2 ưu tiên văn hóa không có chùa, ngày 3 tập trung trải nghiệm địa phương và đi dạo nhẹ nhàng.

    Kỳ vọng: hiểu preference theo từng ngày, không biến tất cả thành global filter.

48. Bỏ các điểm trong nhà, giữ nguyên Bà Nà Hills, thêm một bữa tối đặc sản vào ngày 2 và đừng để ngày nào vượt quá 25 km.

    Kỳ vọng: commit exclusion + required place + distance constraint; phần bữa
    tối xuất hiện trong `unsupported_requests`, không khiến transaction tham quan
    bị rollback và không xuất hiện meal item trong itinerary.

49. Xem lại toàn bộ lịch hiện tại, bỏ các điểm ít phù hợp, không đi tâm linh, giảm thời gian chờ, tránh trùng địa điểm và tự bổ sung điểm nếu còn trống.

    Kỳ vọng: không trả generic `partial`; tự repair đến khi commit hoặc nêu xung đột cụ thể.

50. Tôi muốn 4 ngày quanh Hội An và vùng lân cận, ưu tiên đi bộ, làng nghề, biển và trải nghiệm địa phương; không đi chùa, không lặp điểm và hạn chế tối đa việc đi xa.

    Kỳ vọng: locality-aware planning, đủ 4 ngày, có thể mở rộng bán kính có kiểm soát khi Hội An không đủ candidate.

## F. Câu hỏi chỉ đọc và tính trung thực — 51 đến 55

Tất cả câu trong nhóm này **cần lịch hiện tại** và không được làm thay đổi lịch.

51. Tổng quãng đường của chuyến đi hiện tại là bao nhiêu và ngày nào phải di chuyển nhiều nhất?

    Kỳ vọng: dùng tool đọc, tính từ itinerary và không replan.

52. Lịch trình này có ngày nào quá dày hoặc có khoảng chờ dài không?

    Kỳ vọng: trả lời từ metrics/timeline, không tự sửa khi chưa được yêu cầu.

53. Tổng chi phí ước tính của lịch hiện tại là bao nhiêu? Khoản nào chưa được xác minh?

    Kỳ vọng: không bịa giá, phân biệt estimate và verified data.

54. Vì sao bạn chọn các địa điểm trong ngày 2?

    Kỳ vọng: giải thích dựa trên score, preference và route observation có thật.

55. Trong lịch có địa điểm nào bị trùng hoặc thuộc nhóm tâm linh không?

    Kỳ vọng: kiểm tra dữ liệu thật, không sửa lịch và không trả lời theo suy đoán.

## G. Memory và ngữ cảnh nhiều lượt — 56 đến 60

Các ca này phải chạy **nhiều lượt** với cùng `user_id` và `thread_id`.

56. Lượt 1: Hãy nhớ là tôi không thích đi chùa và thường thích lịch trình nhẹ nhàng.

    Lượt 2: Lên cho tôi chuyến đi 3 ngày ở Huế.

    Kỳ vọng: lưu memory explicit; lượt 2 áp dụng sở thích mà không cần nhắc lại.

57. Lượt 1: Tôi thích biển và thiên nhiên, hãy nhớ sở thích này cho những chuyến sau.

    Lượt 2: Tạo lịch 2 ngày ở Đà Nẵng cho tôi.

    Kỳ vọng: retrieval memory ảnh hưởng candidate điểm tham quan của chuyến mới.

58. Lượt 1: Thêm Chùa Linh Ứng vào ngày 2.

    Lượt 2: Đổi nó sang ngày 1 giúp tôi.

    Kỳ vọng: “nó” tham chiếu Chùa Linh Ứng từ lượt trước và move đúng place.

59. Lượt 1: Bỏ điểm đầu tiên ngày 1.

    Lượt 2: Hoàn tác thay đổi vừa rồi.

    Kỳ vọng: nếu thay đổi lượt 1 đã commit thì agent phải có cơ chế khôi phục snapshot hoặc nói rõ chưa hỗ trợ; không được giả vờ rollback thành công.

60. Lượt 1: Cho tôi xem những gì bạn đang nhớ về sở thích của tôi.

    Lượt 2: Quên sở thích không đi chùa đi.

    Lượt 3: Lên lịch 2 ngày ở Huế.

    Kỳ vọng: list memory, forget đúng memory ID nội bộ qua tool, và lượt 3 không còn áp dụng sở thích đã xóa.

## Cách chấm tổng quát

Mỗi câu được chấm trên năm trục:

- **Hiểu yêu cầu:** mọi vế độc lập đều được chuyển thành constraint/tool action.
- **Tự chủ hợp lý:** tự chọn địa điểm khi locality/preference đã đủ; chỉ hỏi lại khi thiếu tham chiếu thật sự.
- **Tính đúng:** không vi phạm hard constraint, không trùng điểm, đúng locality/ngày;
  yêu cầu ngoài phạm vi phải được phân loại đúng và không làm thay đổi lịch.
- **Chất lượng tuyến:** distance/travel/idle gap không tệ hơn baseline phù hợp.
- **Tính trung thực:** chỉ báo thành công khi đã commit; lỗi phải có nguyên nhân cụ thể, không che bằng thông báo `partial` chung chung.
