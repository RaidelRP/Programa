# importing libraries
from multiprocessing import Semaphore
import socket
import cv2
import pickle
import struct

import numpy as np
import cv2

import pickle

import threading
import logging

import face_recognition

from datos import tracking_general, imagenes, known_face_encodings, known_face_names
import datos
from functions import contar_desconocidos, existe_en_tracking, get_iou, resize, historial, unir_rostros_cuerpos, coincide_rostro_en_tracking, coincide_cuerpo_en_tracking
from metodos_deteccion import coordenadas_yunet_a_facerec, deteccion_personas_yolo

from datetime import datetime

semaforo = Semaphore(1)

logging.basicConfig(level=logging.INFO,
                    format="[%(levelname)s] (%(threadName)-s) %(message)s")


def deteccion_identificacion_rostros(frame, coordenadas_local, rostros, nombre_camara):
    rgb_frame = frame[:, :, ::-1]

    face_locations = face_recognition.face_locations(rgb_frame)
    face_encodings = face_recognition.face_encodings(
        rgb_frame, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        # Persona con nombre, distancia, coordenadas y ttl
        name = "Desconocido"
        p = {"nombre": name,
             "coordenadas_local": coordenadas_local,
             "nombre_camara": nombre_camara,
             "coordenadas_mapa": (0, 0),
             "ttl": 0,
             "coordenadas_rostro": (left, top, right, bottom),
             "distancia_rostro": 0.0,
             "coordenadas_cuerpo": (0, 0, 0, 0),
             "confianza_cuerpo": 0.0}

        matches = face_recognition.compare_faces(
            known_face_encodings, face_encoding)

        face_distances = face_recognition.face_distance(
            known_face_encodings, face_encoding)
        best_match_index = np.argmin(face_distances)
        if matches[best_match_index]:  # Rostros identificados
            name = known_face_names[best_match_index]
            p["nombre"] = name
            p["distancia_rostro"] = face_distances[best_match_index]
            rostros.append(p)

        else:  # Rostros desconocidos
            id = contar_desconocidos()
            myPath = "rostros"
            rostro = frame[top:bottom, left:right]
            name += "_{}".format(id)
            rostro = cv2.resize(rostro, (150, 150),
                                interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(myPath + "\\" + name + ".jpg", rostro)

            image = face_recognition.load_image_file(
                myPath + "\\" + name + ".jpg")

            if (len(face_recognition.face_encodings(image)) > 0):
                face_encoding = face_recognition.face_encodings(image)[0]

                semaforo.acquire()
                known_face_encodings.append(face_encoding)
                known_face_names.append(name)
                semaforo.release()

            cv2.rectangle(frame, (left, top),
                          (right, bottom), datos.ROJO, 2)
            cv2.rectangle(frame, (left, bottom - 35),
                          (right, bottom), datos.ROJO, cv2.FILLED)
            cv2.putText(frame, name, (left + 6, bottom - 6),
                        datos.font, 1.0, datos.BLANCO, 1)


def deteccion_yunet_identificacion_rostros(frame, coordenadas_local, rostros, nombre_camara, detector_yunet):
    rgb_frame = frame[:, :, ::-1]

    img_W = int(frame.shape[1])
    img_H = int(frame.shape[0])

    detector_yunet.setInputSize((img_W, img_H))
    detections = detector_yunet.detect(frame)

    face_locations = coordenadas_yunet_a_facerec(detections)
    face_encodings = face_recognition.face_encodings(
        rgb_frame, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        # Persona con nombre, distancia, coordenadas y ttl
        name = "Desconocido"
        p = {"nombre": name,
             "coordenadas_local": coordenadas_local,
             "nombre_camara": nombre_camara,
             "coordenadas_mapa": (0, 0),
             "ttl": 0,
             "coordenadas_rostro": (left, top, right, bottom),
             "distancia_rostro": 0.0,
             "coordenadas_cuerpo": (0, 0, 0, 0),
             "confianza_cuerpo": 0.0}

        matches = face_recognition.compare_faces(
            known_face_encodings, face_encoding)

        face_distances = face_recognition.face_distance(
            known_face_encodings, face_encoding)

        best_match_index = np.argmin(face_distances)

        if matches[best_match_index]:  # Rostros identificados
            name = known_face_names[best_match_index]
            p["nombre"] = name
            p["distancia_rostro"] = face_distances[best_match_index]
            rostros.append(p)

        else:  # Rostros desconocidos
            id = contar_desconocidos()
            myPath = "rostros"
            rostro = frame[top:bottom, left:right]
            name += "_{}".format(id)
            rostro = cv2.resize(rostro, (150, 150),
                                interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(myPath + "\\" + name + ".jpg", rostro)

            image = face_recognition.load_image_file(
                myPath + "\\" + name + ".jpg")

            if (len(face_recognition.face_encodings(image)) > 0):
                face_encoding = face_recognition.face_encodings(image)[0]

                semaforo.acquire()
                known_face_encodings.append(face_encoding)
                known_face_names.append(name)
                semaforo.release()

            cv2.rectangle(frame, (left, top),
                          (right, bottom), datos.ROJO, 2)
            cv2.rectangle(frame, (left, bottom - 35),
                          (right, bottom), datos.ROJO, cv2.FILLED)
            cv2.putText(frame, name, (left + 6, bottom - 6),
                        datos.font, 1.0, datos.BLANCO, 1)


def seguimiento_cuerpo(cuerpos, nombre_camara):
    for cuerpo in cuerpos:
        # verifico si no se ha incluido en el tracking para insertarla
        if not coincide_cuerpo_en_tracking(cuerpo, tracking_general):
            cuerpo["ttl"] = 10

            semaforo.acquire()
            tracking_general.append(cuerpo)
            semaforo.release()

        for persona_seguida in tracking_general:
            # si se detecta procedente de un local sin camara, asignarle la camara actual
            if cuerpo["nombre"] == persona_seguida["nombre"] and persona_seguida["nombre_camara"] == "NINGUNO":
                semaforo.acquire()
                persona_seguida["nombre_camara"] = nombre_camara
                semaforo.release()

            if get_iou(cuerpo["coordenadas_cuerpo"], persona_seguida["coordenadas_cuerpo"]) > 0.1:

                semaforo.acquire()
                persona_seguida["coordenadas_cuerpo"] = cuerpo["coordenadas_cuerpo"]
                semaforo.release()

                if cuerpo["confianza_cuerpo"] > persona_seguida["confianza_cuerpo"]:

                    semaforo.acquire()

                    persona_seguida["confianza_cuerpo"] = cuerpo["confianza_cuerpo"]
                    persona_seguida["nombre"] = cuerpo["nombre"]

                    semaforo.release()

                semaforo.acquire()
                persona_seguida["ttl"] = 10
                semaforo.release()


def seguimiento_rostro(rostros, nombre_camara):
    for rostro in rostros:
        # verifico si no se ha incluido en el tracking para insertarla
        if not coincide_rostro_en_tracking(rostro, tracking_general):
            rostro["ttl"] = 10

            semaforo.acquire()
            tracking_general.append(rostro)
            semaforo.release()

        for persona_seguida in tracking_general:
            # si se detecta procedente de un local sin camara, asignarle la camara actual
            if rostro["nombre"] == persona_seguida["nombre"] and persona_seguida["nombre_camara"] == "NINGUNO":
                semaforo.acquire()
                persona_seguida["nombre_camara"] = nombre_camara
                semaforo.release()

            if get_iou(rostro["coordenadas_rostro"], persona_seguida["coordenadas_rostro"]) > 0.1:

                semaforo.acquire()
                persona_seguida["coordenadas_rostro"] = rostro["coordenadas_rostro"]
                semaforo.release()

                if rostro["distancia_rostro"] < persona_seguida["distancia_rostro"]:

                    semaforo.acquire()

                    persona_seguida["distancia_rostro"] = rostro["distancia_rostro"]
                    persona_seguida["nombre"] = rostro["nombre"]

                    semaforo.release()

                semaforo.acquire()
                persona_seguida["ttl"] = 10
                semaforo.release()

            # historial(persona_seguida["nombre"])


def seguimiento(rostros, cuerpos, nombre_camara):
    seguimiento_cuerpo(cuerpos, nombre_camara)
    seguimiento_rostro(rostros, nombre_camara)


def rectangulo_nombre_rostros(coordenadas_local, nombre_camara, frame, camara):
    for persona in tracking_general:
        # Si se encuentra en el local actual y la camara actual
        if persona["coordenadas_local"] == coordenadas_local and persona["nombre_camara"] == nombre_camara:
            if persona["coordenadas_cuerpo"] != (0, 0, 0, 0):
                cv2.rectangle(frame,
                              (persona["coordenadas_cuerpo"][0],
                               persona["coordenadas_cuerpo"][1]),
                              (persona["coordenadas_cuerpo"][2],
                               persona["coordenadas_cuerpo"][3]),
                              datos.VERDE, 2)

                cv2.rectangle(frame,
                              (persona["coordenadas_cuerpo"][0],
                               persona["coordenadas_cuerpo"][3] - 35),
                              (persona["coordenadas_cuerpo"][2],
                               persona["coordenadas_cuerpo"][3]),
                              datos.VERDE, cv2.FILLED)
                cv2.putText(frame, persona["nombre"], (persona["coordenadas_cuerpo"][0] + 6, persona["coordenadas_cuerpo"][3] - 6),
                            datos.font, 1.0, datos.BLANCO, 1)

                if persona["ttl"] == 0:
                    i = 0
                    for (top, right, bottom, left) in camara["rectangulos"]:
                        if get_iou(persona["coordenadas_cuerpo"], (top, right, bottom, left)) > 0.1:
                            semaforo.acquire()
                            # persona["coordenadas_rostro"] = camara["rectangulos_relacionados"][i]
                            persona["coordenadas_local"] = camara["locales_relacionados"][i]
                            persona["nombre_camara"] = camara["camaras_relacionadas"][i]
                            persona["ttl"] = 10
                            semaforo.release()
                        i = i + 1


def rectangulos_entrada_salida(camara, frame):
    for (left, top, right, bottom) in camara["rectangulos"]:
        cv2.rectangle(frame, (left, top), (right, bottom), datos.MARRON, 2)


def procesamiento(frame, coordenadas_local, nombre_camara, camara, net, output_layers, detector_yunet):
    rostros = []
    cuerpos = []
    deteccion_yunet_identificacion_rostros(
        frame, coordenadas_local, rostros, nombre_camara, detector_yunet)
    deteccion_personas_yolo(frame, cuerpos, coordenadas_local,
                            nombre_camara, net, output_layers)
    unir_rostros_cuerpos(rostros, cuerpos)
    seguimiento(rostros, cuerpos, nombre_camara)
    rectangulo_nombre_rostros(
        coordenadas_local, nombre_camara, frame, camara)
    # rectangulos_entrada_salida(camara, frame)


def facerec_from_webcam(local, camara, pos):
    video_capture = cv2.VideoCapture(0)
    coordenadas_local = local["coordenadas"]
    nombre_camara = camara["nombre_camara"]

    net_yolo = cv2.dnn.readNet("modelos/yolov3.weights", "modelos/yolov3.cfg")

    layer_names = net_yolo.getLayerNames()
    output_layers = [layer_names[i - 1]
                     for i in net_yolo.getUnconnectedOutLayers()]

    detector_yunet = cv2.FaceDetectorYN.create(
        "modelos/face_detection_yunet_2022mar.onnx", "", (320, 320))

    while True:
        ret, frame = video_capture.read()

        procesamiento(frame, coordenadas_local, nombre_camara,
                      camara, net_yolo, output_layers, detector_yunet)

        semaforo.acquire()
        imagenes[pos] = frame
        semaforo.release()


def facerec_from_video(local, camara, pos, ruta_video):
    video_capture = cv2.VideoCapture(ruta_video)
    coordenadas_local = local["coordenadas"]
    nombre_camara = camara["nombre_camara"]

    net_yolo = cv2.dnn.readNet("modelos/yolov3.weights", "modelos/yolov3.cfg")

    layer_names = net_yolo.getLayerNames()
    output_layers = [layer_names[i - 1]
                     for i in net_yolo.getUnconnectedOutLayers()]

    detector_yunet = cv2.FaceDetectorYN.create(
        "modelos/face_detection_yunet_2022mar.onnx", "", (320, 320))

    while True:
        ret, frame = video_capture.read()

        procesamiento(frame, coordenadas_local, nombre_camara,
                      camara, net_yolo, output_layers, detector_yunet)

        semaforo.acquire()
        imagenes[pos] = frame
        semaforo.release()


def facerec_from_socket(host_ip, port, local, camara, pos):
    # Recibir datos desde las camaras con socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((host_ip, port))
    data = b""
    payload_size = struct.calcsize("Q")

    coordenadas_local = local["coordenadas"]
    nombre_camara = camara["nombre_camara"]

    net_yolo = cv2.dnn.readNet("modelos/yolov3.weights", "modelos/yolov3.cfg")

    layer_names = net_yolo.getLayerNames()
    output_layers = [layer_names[i - 1]
                     for i in net_yolo.getUnconnectedOutLayers()]

    detector_yunet = cv2.FaceDetectorYN.create(
        "modelos/face_detection_yunet_2022mar.onnx", "", (320, 320))

    while True:
        while len(data) < payload_size:
            packet = client_socket.recv(4*1024)
            if not packet:
                break
            data += packet
        packed_msg_size = data[:payload_size]
        data = data[payload_size:]
        msg_size = struct.unpack("Q", packed_msg_size)[0]
        while len(data) < msg_size:
            data += client_socket.recv(4*1024)
        frame_data = data[:msg_size]
        data = data[msg_size:]
        frame = pickle.loads(frame_data)

        procesamiento(frame, coordenadas_local, nombre_camara,
                      camara, net_yolo, output_layers, detector_yunet)

        semaforo.acquire()
        imagenes[pos] = frame
        semaforo.release()

    client_socket.close()


def mostrar_mapa(pos):
    while True:
        img = cv2.imread(datos.mapa)

        i = 0
        for persona in tracking_general:
            cv2.putText(
                img, persona["nombre"], persona["coordenadas_mapa"], datos.font, 0.75, datos.NEGRO, 1)

            if persona["nombre_camara"] != "NINGUNO":
                semaforo.acquire()
                persona["ttl"] = persona["ttl"] - 1
                semaforo.release()

            x_mapa = persona["coordenadas_local"][0] + 40
            y_mapa = persona["coordenadas_local"][1] + i*25 + 40

            semaforo.acquire()
            persona["coordenadas_mapa"] = (x_mapa, y_mapa)
            semaforo.release()

            if persona["ttl"] < 0:
                semaforo.acquire()
                tracking_general.remove(persona)
                semaforo.release()

            i = i + 1

        # logging.info(tracking_general)

        semaforo.acquire()
        imagenes[pos] = img
        semaforo.release()


def mostrar_imagenes():
    while True:
        semaforo.acquire()

        imagenes[0] = resize(imagenes[0], height=840, width=597)
        imagenes[1] = resize(imagenes[1], height=280, width=373)
        imagenes[2] = resize(imagenes[2], height=280, width=373)
        imagenes[3] = resize(imagenes[3], height=280, width=373)

        concat_v = cv2.vconcat([imagenes[1], imagenes[2], imagenes[3]])
        concat_h = cv2.hconcat([imagenes[0], concat_v])

        semaforo.release()

        cv2.imshow("Mapa y camaras", concat_h)
        if cv2.waitKey(30) & 0xFF == ord("q"):
            break


# hilo1 = threading.Thread(target=facerec_from_video,
#                          args=(datos.LOCAL3, datos.CAM1, 1, "hamilton_clip.mp4"), name="CAMARA 1")
hilo2 = threading.Thread(target=facerec_from_socket,
                         args=("10.30.125.149", 10500, datos.LOCAL2, datos.CAM2, 2), name="CAMARA 2")
hilo3 = threading.Thread(target=facerec_from_socket,
                         args=("10.30.125.150", 10510, datos.LOBBY, datos.CAM2, 3), name="CAMARA 3")
hilo4 = threading.Thread(target=mostrar_mapa, args=(0,), name="PLANO")
hilo5 = threading.Thread(target=mostrar_imagenes, name="VISUALIZACION")

# hilo1.start()
hilo2.start()
hilo3.start()
hilo4.start()
hilo5.start()

# hilo1.join()
hilo2.join()
hilo3.join()
hilo4.join()
hilo5.join()

cv2.destroyAllWindows()
