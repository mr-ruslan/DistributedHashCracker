#  Задание
Мы стремимся реализовать распределенную систему для взлома хэша под кодовым именем CrackHash. Непосредственно взлом хэша будем реализовывать через простой перебор словаря сгенерированного на основе алфавита (brute-force). В общих чертах система должна работать по следующей логике:
В рамках системы существует менеджер, который принимает от пользователя запрос, содержащий MD-5 хэш некоторого слова, а также его максимальную длину.
Менеджер обрабатывает запрос: генерирует задачи в соответствии с заданным числом воркеров (вычислительных узлов) на перебор слов составленных из переданного им алфавита. После чего отправляет их на исполнение воркерам. 
Каждый воркер принимает задачу, перебирает слова в заданном диапазоне и вычисляет их хэш. Находит слова у которых хеш совпадает с заданным, и результат работы возвращает менеджеру через очередь.

# Task 2.  Fault tolerance
В рамках второй лабораторной работы необходимо модифицировать систему таким образом, чтобы обеспечить гарантированную обработку запроса пользователя (если доступен менеджер) т.е. обеспечить отказоустойчивость системы в целом.

## Основные требования:
1. Обеспечить сохранность данных при отказе работы менеджера
* Для этого необходимо обеспечить хранение данных об обрабатываемых запросах в базе данных
* Также необходимо организовать взаимодействие воркеров с менеджером через очередь RabbitMQ
    + Для этого достаточно настроить очередь с direct exchange-ем
    + Если менеджер недоступен, то сообщения должны сохраняться в очереди до момента возобновления его работы
* RabbitMQ также необходимо разместить в окружении docker-compose
2. Обеспечить частичную отказоустойчивость базы данных
* База данных также должна быть отказоустойчивой, для этого требуется реализовать простое реплицирование для нереляционной базы MongoDB
* Минимально рабочая схема одна primary нода, две secondary
* Менеджер должен отвечать клиенту, что задача принята в работу только после того, как она была успешно сохранена в базу данных и отреплицирована
3. Обеспечить сохранность данных при отказе работы воркера(-ов)
* В docker-compose необходимо разместить, как минимум, 2 воркера
* Организовать взаимодействие менеджера с воркерами через очередь RabbitMQ (вторая, отдельная очередь), аналогично настроить direct exchange
* В случае, если любой из воркеров при работе над задачей ”cломался” и не отдал ответ, то задача должна быть переотправлена другому воркеру, для этого необходимо корректно настроить механизм acknowledgement-ов
* Если на момент создания задач нет доступных воркеров, то сообщения должны дождаться их появления в очереди, а затем отправлены на исполнение
4. Обеспечить сохранность данных при отказе работы очереди
* Если менеджер не может отправить задачи в очередь, то он должен сохранить их у себя в базе данных до момента восстановления доступности очереди, после чего снова отправить накопившиеся задачи
* Очередь не должна терять сообщения при рестарте (или падении из-за ошибки), для этого все сообщения должны быть персистентными (это регулируется при их отправке)

## Кейсы, которые будут проверяться:
1. стоп сервиса менеджера в docker-compose 
* полученные ранее ответы от воркеров должны быть сохранены в базу и не должны потеряться
* не дошедшие до менеджера ответы на задачи не должны потеряться, менеджер должен подобрать их при рестарте
2. стоп primary ноды реплик-сета MongoDB в docker-compose 
* primary нода должна измениться, в система продолжать работу в штатном режиме
3. стоп RabbitMQ в docker-compose
* все необработанные, на момент выключения очереди, сообщения после рестарта не должны потеряться
4. стоп воркера во время обработки задачи
* сообщение должно быть переотправлено другому воркеру, задача не должна быть потеряна