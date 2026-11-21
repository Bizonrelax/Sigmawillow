---
id: GVK-SKEL-JAVA
file: SKEL_JAVA.md
etymology: SKEL_JAVA = каркас своего стека; грузится только тот, кто работает на этом стеке.
desc: Каркас java: pom.xml с пинами, workflow maven.yml с jpackage app-image и Windows-ZIP, проверка каркаса, лицензионные ловушки JDK.
name: SKEL_JAVA — каркас стека
F: каркас
Q: полный
N: [gvk, каркас, ci, java]
O: практический
T: активен, v5.2
---

### SKEL_JAVA.md — КАРКАС СТЕКА JAVA

Грузится вместе с SKELETON.md только тем, чей стек — java. Общие правила каркаса и приёмка — SKELETON.md K1, K3, K9; критерии поставки — STACK.md ST1.

K2.0. Бутстрап окружения (C3.1). Выполняется после общей части C3.0, один вызов:

```bash
java
```

K2. pom.xml (стек java)

Имена для java: `artifactId` = имя репозитория в нижнем регистре, только `[a-z0-9]`; если начинается с цифры — добавить префикс `p`. Пакет = `io.github.bizonrelax.<artifactId>`. Главный класс = `Main`. Рантайм — Temurin или Liberica, не Oracle JDK по умолчанию. Spring Boot — только если ТЗ требует HTTP-интерфейс. Упаковка — `jpackage --type app-image`, Launch4j запрещён.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>io.github.bizonrelax</groupId>
  <artifactId>ARTIFACT_ID</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>
  <name>REPO_NAME</name>
  <description>ОДНА СТРОКА ИЗ ТЗ</description>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <main.class>io.github.bizonrelax.ARTIFACT_ID.Main</main.class>
    <junit.version>5.10.2</junit.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <finalName>${project.artifactId}</finalName>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
          <argLine>-Dfile.encoding=UTF-8 -Djava.awt.headless=true</argLine>
          <excludedGroups>gui</excludedGroups>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.5.3</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>${main.class}</mainClass>
                </transformer>
              </transformers>
              <filters>
                <filter>
                  <artifact>*:*</artifact>
                  <excludes>
                    <exclude>META-INF/*.SF</exclude>
                    <exclude>META-INF/*.DSA</exclude>
                    <exclude>META-INF/*.RSA</exclude>
                    <exclude>module-info.class</exclude>
                  </excludes>
                </filter>
              </filters>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

Тесты, требующие окна, помечать `@Tag("gui")` — они исключены из прогона и проверяются вручную на Windows.

Если ТЗ требует HTTP-интерфейс: parent `spring-boot-starter-parent`, зависимости `spring-boot-starter-web` и `spring-boot-starter-test`, плагин `spring-boot-maven-plugin` с целью `repackage`, shade не использовать. Порт в тестах случайный (`@SpringBootTest(webEnvironment = RANDOM_PORT)`), в программе — из `PLAN.md`.

K4. .github/workflows/maven.yml

```yaml
name: maven
on:
  push:
    branches: [ main, 'gvk/**' ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main ]
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.ref_type != 'tag' }}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Build and test
        run: mvn -B -ntp verify
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: surefire-reports
          path: target/surefire-reports/
          if-no-files-found: ignore
  windows-portable:
    needs: test
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Package jar
        run: mvn -B -ntp -DskipTests package
      - name: jpackage app-image
        shell: pwsh
        run: |
          $app = "${{ github.event.repository.name }}"
          New-Item -ItemType Directory -Force -Path target/app | Out-Null
          Get-ChildItem target/*.jar -Exclude 'original-*' | Select-Object -First 1 | Copy-Item -Destination target/app/app.jar
          jpackage --type app-image --name $app --input target/app --main-jar app.jar --dest dist --java-options "-Dfile.encoding=UTF-8" --java-options "-Dsun.stdout.encoding=UTF-8" --java-options "-Dsun.stderr.encoding=UTF-8"
      - name: Zip portable folder
        shell: pwsh
        run: |
          $app = "${{ github.event.repository.name }}"
          Compress-Archive -Path "dist/$app/*" -DestinationPath "$app-windows-portable.zip" -Force
      - uses: actions/upload-artifact@v4
        with:
          name: ${{ github.event.repository.name }}-windows-portable
          path: ${{ github.event.repository.name }}-windows-portable.zip
      - name: Attach to release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: ${{ github.event.repository.name }}-windows-portable.zip
```

Правила сборки: `--type app-image` не требует WiX и даёт папку с EXE и встроенным рантаймом; типы `exe` и `msi` не использовать. `--main-class` не указывать — jpackage берёт `Main-Class` из манифеста, это работает и для shade-jar, и для Spring Boot. Консольной программе добавить `--win-console`. Windows-пакет собирается только на windows-раннере: jpackage не умеет кросс-сборку. Launch4j не использовать. Релиз: тег `vX.Y.Z` → workflow прикрепляет ZIP.

K5. Проверка каркаса java. Локально `mvn -B -ntp verify` → Failures: 0, Errors: 0. Workflow проверяется запуском CI после пуша, результат в отчёт. Красный CI = фрагмент 000 не завершён.

Ловушки стоимости стека java (ST4). Рантайм — Temurin или Liberica (GPLv2+CE), бесплатно и свободно распространяемо; Oracle JDK с условиями NFTC по умолчанию не брать. Launch4j запрещён: он не вкладывает рантайм, и на чужом компьютере программа не запустится. JavaFX-сборки проверять на лицензии отдельных артефактов. Поставка `jpackage --type app-image` содержит рантайм внутри папки — это и есть выполнение ST1, пункты 2–5.
